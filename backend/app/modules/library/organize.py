"""AI 整理闭环与研究入库提案应用器（工单 05）。

两层结构（spec 用户故事 24~26）：确定性检测（重复组 / 处理异常，零 LLM）
先暴露机械问题；语义整理（结构化标题与 Course 归类建议）才走 LLM，产出
ORGANIZE 提案逐条确认应用——拒绝不改事实。提案应用器在本模块注册进
ProposalService 注册表（routes 导入本模块即完成注册）。
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.ingest import create_web_ingest_rows, valid_course
from app.modules.course.models import Course
from app.modules.library.models import AgentProposal, LibraryItem
from app.modules.library.proposals import register_applier
from app.modules.library.schemas import (
    AgentProposalOut,
    LibraryAvailability,
    LibraryItemOut,
    OrganizeDuplicateGroup,
    OrganizePayload,
    OrganizeProposeOut,
    OrganizeScanOut,
    OrganizeSuggestionBatch,
    ProposalStatus,
    ProposalType,
    ResearchIngestPayload,
)
from app.modules.library.service import LibraryService
from app.modules.llm.service import (
    StructuredGenerationError,
    StructuredModel,
    call_organize_model,
)
from app.modules.settings.config import load_llm_provider
from app.shared.errors import CodedHTTPException

ORGANIZE_PROMPT_VERSION = "library-organize-v1"

OrganizeGenerator = Callable[[str], Awaitable[OrganizeSuggestionBatch]]


def _payload_dict(raw: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw)
    except ValueError:
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def build_organize_prompt(items: list[tuple[str, str, str]], courses: list[tuple[str, str]]) -> str:
    """LLM 输入：条目清单 + 课程清单。只喂 id/标题/来源类型，不喂正文。"""
    item_lines = "\n".join(
        f"- id={item_id} 标题={title} 来源={source_type}" for item_id, title, source_type in items
    )
    course_lines = "\n".join(f"- id={course_id} 名称={name}" for course_id, name in courses)
    return (
        "你是学习资料库的整理助手。下面是资料条目清单与可选的课程清单。\n"
        "请只为「需要整理」的条目给出建议：标题不规范（乱码、截断、无意义后缀、"
        "英文域名占位）的给出规范化标题；未归类或归类明显不当的给出最合适的一个"
        "课程（course_id 必须来自清单，都不合适则不填）。\n"
        "已经规范的条目不要输出；不要发明不存在的 course_id；不建议改变条目内容本身。\n\n"
        f"资料条目：\n{item_lines}\n\n课程清单：\n{course_lines}\n"
    )


class OrganizeService:
    @staticmethod
    async def scan(session: AsyncSession) -> OrganizeScanOut:
        """确定性检测（零 LLM）：未软删 ACTIVE 条目中的重复哈希组与失败条目。"""
        items = list(
            (
                await session.scalars(
                    select(LibraryItem)
                    .where(LibraryItem.deleted_at.is_(None), LibraryItem.status == "ACTIVE")
                    .order_by(LibraryItem.updated_at.desc(), LibraryItem.id.desc())
                )
            ).all()
        )
        outs = await LibraryService.compose_outs(session, items)
        out_by_id = {out.id: out for out in outs}
        by_hash: dict[str, list[LibraryItemOut]] = {}
        for item in items:
            by_hash.setdefault(item.content_hash, []).append(out_by_id[item.id])
        duplicates = [
            OrganizeDuplicateGroup(content_hash=content_hash, items=members)
            for content_hash, members in by_hash.items()
            if len(members) >= 2
        ]
        return OrganizeScanOut(
            duplicates=duplicates,
            failed_items=[out for out in outs if out.availability == LibraryAvailability.FAILED],
            unclassified=[out for out in outs if out.course_id is None],
        )

    @staticmethod
    async def propose_with_llm(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        organize_model: StructuredModel,
    ) -> OrganizeProposeOut:
        """路由入口：供应商校验 + LLM 调用 + 提案落库（fastapi.md §1 薄路由）。"""
        provider = await asyncio.to_thread(load_llm_provider, data_dir)
        if provider is None or not provider.api_key:
            raise CodedHTTPException(
                code="LLM_PROVIDER_UNCONFIGURED",
                status_code=409,
                detail="请先配置包含密钥的 LLM Provider",
            )

        async def generate(prompt: str) -> OrganizeSuggestionBatch:
            try:
                return await call_organize_model(
                    session_factory=session_factory,
                    organize_model=organize_model,
                    provider=provider,
                    prompt=prompt,
                    prompt_version=ORGANIZE_PROMPT_VERSION,
                )
            except StructuredGenerationError as exc:
                raise CodedHTTPException(
                    code="LLM_OUTPUT_INVALID",
                    status_code=502,
                    detail="AI 整理建议生成失败，请稍后重试",
                ) from exc

        return await OrganizeService.propose(session_factory, generate)

    @staticmethod
    async def propose(
        session_factory: async_sessionmaker[AsyncSession],
        generate: OrganizeGenerator,
    ) -> OrganizeProposeOut:
        """LLM 生成 ORGANIZE 提案：generate 为结构化生成协程（测试可注 fake）。"""
        async with session_factory() as session:
            items = list(
                (
                    await session.scalars(
                        select(LibraryItem)
                        .where(
                            LibraryItem.deleted_at.is_(None),
                            LibraryItem.status == "ACTIVE",
                        )
                        .order_by(LibraryItem.updated_at.desc(), LibraryItem.id.desc())
                    )
                ).all()
            )
            courses = (
                await session.execute(
                    select(Course.id, Course.name).where(
                        Course.deleted_at.is_(None), Course.status == "ACTIVE"
                    )
                )
            ).all()
        if not items:
            return OrganizeProposeOut(created=[], skipped=[])
        prompt = build_organize_prompt(
            [(item.id, item.title, item.source_type) for item in items],
            [(cast(str, cid), name) for cid, name in courses],
        )
        batch = await generate(prompt)
        course_ids = {cast(str, cid) for cid, _name in courses}
        item_ids = {item.id for item in items}
        created: list[AgentProposalOut] = []
        skipped: list[str] = []
        now = utcnow()
        async with session_factory() as session, session.begin():
            for suggestion in batch.suggestions:
                if suggestion.item_id not in item_ids:
                    skipped.append(suggestion.item_id)
                    continue
                if suggestion.course_id is not None and suggestion.course_id not in course_ids:
                    suggestion.course_id = None  # 幻觉 course：降级为仅标题建议
                payload: dict[str, object] = {"item_id": suggestion.item_id}
                if suggestion.title is not None:
                    payload["title"] = suggestion.title.strip()
                if suggestion.course_id is not None:
                    payload["course_id"] = suggestion.course_id
                if len(payload) == 1:
                    continue  # 无可应用字段
                proposal = AgentProposal(
                    id=str(uuid4()),
                    proposal_type=ProposalType.ORGANIZE.value,
                    status=ProposalStatus.PENDING.value,
                    target_type="library_item",
                    target_id=suggestion.item_id,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=now,
                )
                session.add(proposal)
                await session.flush()
                created.append(
                    AgentProposalOut(
                        id=proposal.id,
                        proposal_type=ProposalType.ORGANIZE,
                        status=ProposalStatus.PENDING,
                        session_id=None,
                        message_id=None,
                        target_type=proposal.target_type,
                        target_id=proposal.target_id,
                        payload=payload,
                        evidence_refs=None,
                        error_code=None,
                        created_at=proposal.created_at,
                        decided_at=None,
                    )
                )
        return OrganizeProposeOut(created=created, skipped=skipped)


async def apply_organize(session: AsyncSession, proposal: AgentProposal) -> None:
    """ORGANIZE 应用器：标题 / 归类建议落到条目（确认后原子应用）。"""
    payload = OrganizePayload.model_validate(_payload_dict(proposal.payload_json))
    item = await LibraryService.active_item(session, payload.item_id)
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise CodedHTTPException(
                code="LIBRARY_PATCH_EMPTY", status_code=422, detail="建议标题不能为空"
            )
        item.title = title
    if payload.course_id is not None:
        await valid_course(session, payload.course_id)
        item.course_id = payload.course_id
    item.updated_at = utcnow()


async def apply_research_ingest(session: AsyncSession, proposal: AgentProposal) -> None:
    """RESEARCH_INGEST 应用器：确认后经业务入库创建资料条目与 WEB_FETCH 任务。

    payload 的标题作为条目初始展示标题（抓取成功后被页面真标题覆盖）；
    搜索摘要不成为资料事实（正文只来自真实抓取）；未成功抓取前不进 RAG
    （分片由 web_fetch_worker 成功写回时才产生）、不生成锚点。Summary 入队
    同理由抓取成功的 writeback 自然触发，此处零特判。
    """
    payload = ResearchIngestPayload.model_validate(_payload_dict(proposal.payload_json))
    await create_web_ingest_rows(
        session,
        payload.url,
        payload.course_id,
        allow_duplicate=False,
        title=payload.title,
    )


register_applier(ProposalType.ORGANIZE, apply_organize)
register_applier(ProposalType.RESEARCH_INGEST, apply_research_ingest)
