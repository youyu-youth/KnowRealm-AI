"""LearnerProfileService（工单 06，ADR-0025）：学习者记忆的受治理读写与 Learner
Context 确定性聚合。

事实源 = learner_preferences 单例行（id='me'，0026 已建表）：
- ``user_selected_preference`` 存 ``{"items": [...]}``——用户显式偏好，仅两个
  写入口：学习画像直编（PUT，立即生效）与 EXPLICIT MEMORY 提案确认后并入；
- ``observed_learning_preference`` 存 ``{"entries": {key: value}}``——结构化
  学习证据推导的观察偏好，仅 OBSERVED MEMORY 提案经确认写入；与显式列物理
  隔离，观察写入路径不触碰显式列，结构上不可能覆盖用户显式偏好。

Learner Context 由 ``build_learner_context`` 在 Agent 运行前确定性构建：全局
偏好可跨会话注入，课程掌握状态只进对应课程范围（RECORD/LIBRARY_ITEM 取挂载
对象所属课程），ALL 只取全局偏好；注入前提 = 外发开关开启且 LLM 外发同意
对当前供应商有效。只影响解释方式与建议，不改任何确定性数值。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course_brain.models import Concept
from app.modules.learner.schemas import (
    LearnerPreferenceOut,
    LearnerPreferenceUpdate,
    MemoryOutboundOut,
)
from app.modules.learning.mastery import MasteryStatus, classify_status
from app.modules.learning.models import UserConceptMastery
from app.modules.library.models import AgentProposal, LearnerPreference
from app.modules.library.schemas import ChatScope, MemoryProposalPayload
from app.modules.settings.config import (
    llm_consent,
    memory_outbound_enabled,
    set_memory_outbound_enabled,
)
from app.shared.errors import CodedHTTPException

CONCEPT_STATUS_CONFIRMED = "CONFIRMED"
# 课程学习状态的注入口径：薄弱概念名单上限（掌握度摘要只给最小必要集合）。
WEAK_CONCEPT_NAMES_LIMIT = 5
# Learner Context 字符预算（spec：限长、可重建；个人量级偏好的宽松上限）。
LEARNER_CONTEXT_MAX_CHARS = 2000


@dataclass(frozen=True)
class LearnerContext:
    """本轮注入 Agent 的学习者记忆（text 进 SYSTEM；memories 供 UI 展示）。"""

    text: str  # 空串 = 本轮无记忆注入
    memories: tuple[str, ...] = ()


def _read_json_object(raw: str) -> dict[str, Any]:
    value: object = json.loads(raw)
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _read_items(row: LearnerPreference | None) -> list[str]:
    if row is None:
        return []
    items = _read_json_object(row.user_selected_preference).get("items", [])
    return [item for item in items if isinstance(item, str)]


def _read_entries(row: LearnerPreference | None) -> dict[str, str]:
    if row is None or row.observed_learning_preference is None:
        return {}
    entries = _read_json_object(row.observed_learning_preference).get("entries", {})
    return {
        key: value
        for key, value in entries.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


async def _ensure_row(session: AsyncSession) -> LearnerPreference:
    row = await session.get(LearnerPreference, "me")
    if row is None:
        row = LearnerPreference(id="me", user_selected_preference="{}", updated_at=utcnow())
        session.add(row)
        await session.flush()
    return row


def _memory_outbound_out(data_dir: Path) -> MemoryOutboundOut:
    granted_at, consent_current = llm_consent(data_dir)
    return MemoryOutboundOut(
        enabled=memory_outbound_enabled(data_dir),
        consent_granted_at=granted_at,
        consent_current=consent_current,
    )


def _preference_out(row: LearnerPreference, data_dir: Path) -> LearnerPreferenceOut:
    return LearnerPreferenceOut(
        explicit_items=_read_items(row),
        observed_entries=_read_entries(row),
        observed_confidence=row.observed_confidence,
        evidence_count=row.evidence_count,
        last_observed_at=row.last_observed_at,
        updated_at=row.updated_at,
        memory_outbound=_memory_outbound_out(data_dir),
    )


async def apply_memory_proposal(
    session: AsyncSession, proposal: AgentProposal
) -> dict[str, object]:
    """MEMORY 提案应用器（learner/routes 导入即注册）：调用方事务内写入。

    EXPLICIT = 条目并入显式偏好（保序去重，已存在则零新增）；OBSERVED =
    整体刷新观察偏好（条目并集 + 置信度/证据数/时间），不触碰显式列。
    """
    payload = MemoryProposalPayload.model_validate(json.loads(proposal.payload_json))
    row = await _ensure_row(session)
    if payload.kind == "EXPLICIT":
        current = _read_items(row)
        merged = _dedupe(current + payload.items)
        if merged == current:
            return {"applied_items": []}
        row.user_selected_preference = json.dumps({"items": merged}, ensure_ascii=False)
        row.updated_at = utcnow()
        return {"applied_items": _dedupe(payload.items)}
    entries = _read_entries(row)
    entries.update(payload.entries)
    row.observed_learning_preference = json.dumps({"entries": entries}, ensure_ascii=False)
    row.observed_confidence = payload.confidence
    row.evidence_count = payload.evidence_count or 0
    row.last_observed_at = utcnow()
    row.updated_at = utcnow()
    return {"applied_entries": sorted(payload.entries)}


async def _course_mastery_summary(
    session: AsyncSession, course_id: str
) -> tuple[dict[str, int], list[str]]:
    """课程掌握状态摘要（CONFIRMED 概念 × 快照派生状态）：计数 + 薄弱概念名单。

    状态经 Mastery Engine 同源纯函数 classify_status 派生（无快照即
    NOT_ENOUGH_DATA）；只读聚合，不改任何确定性数值。
    """
    rows = (
        await session.execute(
            select(
                Concept.canonical_name,
                UserConceptMastery.mastery_score,
                UserConceptMastery.mastery_confidence,
            )
            .outerjoin(UserConceptMastery, UserConceptMastery.concept_id == Concept.id)
            .where(Concept.course_id == course_id, Concept.status == CONCEPT_STATUS_CONFIRMED)
            .order_by(Concept.canonical_name, Concept.id)
        )
    ).all()
    counts = {status.value: 0 for status in MasteryStatus}
    weak_names: list[str] = []
    for name, score, confidence in rows:
        status = classify_status(score, confidence)
        counts[status.value] += 1
        if status is MasteryStatus.WEAK and len(weak_names) < WEAK_CONCEPT_NAMES_LIMIT:
            weak_names.append(str(name))
    return counts, weak_names


def _format_context(
    explicit: list[str], observed: dict[str, str], course_line: str | None
) -> LearnerContext:
    """组装注入文本与 UI 记忆清单：逐条累计，超出预算先到先得。"""
    memories = [
        *explicit,
        *(f"{key}：{value}" for key, value in observed.items()),
    ]
    if course_line is not None:
        memories.append(course_line)
    if not memories:
        return LearnerContext(text="")
    kept: list[str] = []
    used = 0
    for memory in memories:
        if kept and used + len(memory) + 3 > LEARNER_CONTEXT_MAX_CHARS:
            break
        kept.append(memory)
        used += len(memory) + 3  # "- " 前缀 + 换行
    text = (
        "学习者记忆（用户确认或系统观察的稳定偏好与状态，用于调整讲解方式与建议；"
        "不是资料事实，不得当作资料内容引用）：\n" + "\n".join(f"- {memory}" for memory in kept)
    )
    return LearnerContext(text=text, memories=tuple(kept))


async def build_learner_context(
    session: AsyncSession,
    *,
    scope: ChatScope,
    course_id: str | None,
    injection_allowed: bool,
) -> LearnerContext:
    """按会话范围聚合 Learner Context（Agent 运行前调用，确定性、可重建）。

    - ``injection_allowed`` = 外发开关开启且 LLM 外发同意对当前供应商有效；
      关闭即零注入（记忆保留本地），硬门禁「关闭外发后零发送」的实现点；
    - 全局偏好（显式 + 观察）可跨会话；课程状态只进对应课程范围
      （scope != ALL 且 course_id 非 None）；ALL 只取全局偏好。
    """
    if not injection_allowed:
        return LearnerContext(text="")
    row = await session.get(LearnerPreference, "me")
    explicit = _read_items(row)
    observed = _read_entries(row)
    course_line: str | None = None
    if scope is not ChatScope.ALL and course_id is not None:
        counts, weak_names = await _course_mastery_summary(session, course_id)
        total = sum(counts.values())
        if total > 0:
            detail = f"其中薄弱 {counts['WEAK']} 个"
            if weak_names:
                detail += f"（{'、'.join(weak_names)}）"
            course_line = (
                f"当前课程学习状态：已确认概念 {total} 个，{detail}；"
                "讲解薄弱概念时多举贴近用户的例子。"
            )
    return _format_context(explicit, observed, course_line)


class LearnerProfileService:
    @staticmethod
    async def get_preferences(session: AsyncSession, data_dir: Path) -> LearnerPreferenceOut:
        async with session.begin():
            row = await _ensure_row(session)
        return _preference_out(row, data_dir)

    @staticmethod
    async def update_preferences(
        session: AsyncSession, body: LearnerPreferenceUpdate, data_dir: Path
    ) -> LearnerPreferenceOut:
        async with session.begin():
            row = await _ensure_row(session)
            row.user_selected_preference = json.dumps(
                {"items": _dedupe(body.items)}, ensure_ascii=False
            )
            row.updated_at = utcnow()
        return _preference_out(row, data_dir)

    @staticmethod
    async def delete_observed(session: AsyncSession, key: str) -> None:
        async with session.begin():
            row = await _ensure_row(session)
            entries = _read_entries(row)
            if key not in entries:
                raise CodedHTTPException(
                    code="LEARNER_OBSERVED_KEY_NOT_FOUND",
                    status_code=404,
                    detail="观察偏好不存在或已删除",
                )
            del entries[key]
            row.observed_learning_preference = json.dumps({"entries": entries}, ensure_ascii=False)
            row.updated_at = utcnow()

    @staticmethod
    def set_memory_outbound(data_dir: Path, enabled: bool) -> MemoryOutboundOut:
        set_memory_outbound_enabled(data_dir, enabled)
        return _memory_outbound_out(data_dir)
