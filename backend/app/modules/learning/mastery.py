"""Concept Mastery V1 纯函数算法（零 LLM、零 IO、确定性）。

只消费带主概念与可判定分数的 Quiz Evidence：按 ``occurred_at`` 倒序取最近
``WINDOW_SIZE`` 条，以四条为半衰跨度做序位加权；置信度表示证据充足程度而非成绩
好坏；不读取墙钟时间、不随难度权重变化。算法调整必须新增版本号并全量重建。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

ALGORITHM_VERSION = "mastery_v1"

WINDOW_SIZE = 12
RANK_HALF_LIFE = 4
# 标准 Quiz 单条有效计数分母：weight 0.9 × confidence 0.8 = 0.72。
BASE_EFFECTIVE_WEIGHT = 0.72
MIN_EVIDENCE_COUNT = 3
WEAK_SCORE_MAX = 0.50
STABLE_SCORE_MIN = 0.80
HIGH_CONFIDENCE_EFFECTIVE_COUNT = 8
MEDIUM_CONFIDENCE_EFFECTIVE_COUNT = 5

POSITIVE_RESULT = "CORRECT"
NEGATIVE_RESULT = "WRONG"


class MasteryStatus(StrEnum):
    """V1 四态：AT_RISK / MISCONCEPTION_RISK 留给 Forgetting 与 Misconception。"""

    NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"
    WEAK = "WEAK"
    LEARNING = "LEARNING"
    STABLE = "STABLE"


class MasteryConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class MasteryEvidence:
    """参与计算的单条有效 Quiz 证据（已过滤：概念归属、分数、Record 未删除）。"""

    evidence_id: str
    score: float
    weight: float
    confidence: float
    result: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class MasteryComputation:
    """一次全量重算结果；NOT_ENOUGH_DATA 时分数与 Confidence 均为空。"""

    status: MasteryStatus
    score: float | None
    confidence_value: float | None
    confidence: MasteryConfidence | None
    evidence_count: int
    positive_evidence_count: int
    negative_evidence_count: int
    last_practiced_at: datetime | None
    last_verified_at: datetime | None


def confidence_level_of(confidence_value: float) -> MasteryConfidence:
    """由 0~1 置信度反推分档：有效计数 3~4 低 / 5~7 中 / 8 及以上高。"""
    effective_count = confidence_value * HIGH_CONFIDENCE_EFFECTIVE_COUNT
    if effective_count >= HIGH_CONFIDENCE_EFFECTIVE_COUNT:
        return MasteryConfidence.HIGH
    if effective_count >= MEDIUM_CONFIDENCE_EFFECTIVE_COUNT:
        return MasteryConfidence.MEDIUM
    return MasteryConfidence.LOW


def classify_status(score: float | None, confidence_value: float | None) -> MasteryStatus:
    """状态规则（查询时回读快照同用）：空分数、弱、稳定、其余学习中的顺序判定。"""
    if score is None or confidence_value is None:
        return MasteryStatus.NOT_ENOUGH_DATA
    if score < WEAK_SCORE_MAX:
        return MasteryStatus.WEAK
    if score >= STABLE_SCORE_MIN and confidence_level_of(confidence_value) is not (
        MasteryConfidence.LOW
    ):
        return MasteryStatus.STABLE
    return MasteryStatus.LEARNING


def window_evidence(evidence: list[MasteryEvidence]) -> list[MasteryEvidence]:
    """最近 12 条窗口（唯一口径）：按 ``occurred_at`` 倒序、稳定 ID 打破平局。

    重算与详情查询共用本函数，保证「参与计算」列表与快照永远同口径。
    """
    return sorted(
        evidence,
        key=lambda item: (item.occurred_at, item.evidence_id),
        reverse=True,
    )[:WINDOW_SIZE]


def compute_mastery(evidence: list[MasteryEvidence]) -> MasteryComputation:
    """从有效证据全量计算快照：窗口截断、序位加权、计数与状态分类。"""
    ordered = window_evidence(evidence)
    positive_count = sum(1 for item in ordered if item.result == POSITIVE_RESULT)
    negative_count = sum(1 for item in ordered if item.result == NEGATIVE_RESULT)
    last_practiced_at = ordered[0].occurred_at if ordered else None
    verified_times = [item.occurred_at for item in ordered if item.result == POSITIVE_RESULT]
    last_verified_at = max(verified_times) if verified_times else None

    if len(ordered) < MIN_EVIDENCE_COUNT:
        return MasteryComputation(
            status=MasteryStatus.NOT_ENOUGH_DATA,
            score=None,
            confidence_value=None,
            confidence=None,
            evidence_count=len(ordered),
            positive_evidence_count=positive_count,
            negative_evidence_count=negative_count,
            last_practiced_at=last_practiced_at,
            last_verified_at=last_verified_at,
        )

    weighted_score = 0.0
    weight_sum = 0.0
    effective_count = 0.0
    for rank, item in enumerate(ordered):
        rank_weight = 0.5 ** (rank / RANK_HALF_LIFE)
        effective_weight = rank_weight * item.weight * item.confidence
        weighted_score += item.score * effective_weight
        weight_sum += effective_weight
        effective_count += item.weight * item.confidence
    score = weighted_score / weight_sum
    confidence_value = min(
        1.0, effective_count / BASE_EFFECTIVE_WEIGHT / HIGH_CONFIDENCE_EFFECTIVE_COUNT
    )
    confidence = confidence_level_of(confidence_value)
    status = classify_status(score, confidence_value)
    return MasteryComputation(
        status=status,
        score=score,
        confidence_value=confidence_value,
        confidence=confidence,
        evidence_count=len(ordered),
        positive_evidence_count=positive_count,
        negative_evidence_count=negative_count,
        last_practiced_at=last_practiced_at,
        last_verified_at=last_verified_at,
    )
