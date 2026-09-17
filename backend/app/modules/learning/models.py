from datetime import datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class LearningEvidence(Base):
    """学习证据：由学习事件经确定性映射派生的可再生数据，可整表清空重放重建。

    event_id 唯一 = 重放幂等的数据库级保障；追加型不软删（无 deleted_at）。
    """

    __tablename__ = "learning_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36))
    concept_id: Mapped[str | None] = mapped_column(String(36), default=None)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    evidence_type: Mapped[str] = mapped_column(String(30))
    result: Mapped[str | None] = mapped_column(Text, default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    difficulty: Mapped[str | None] = mapped_column(String(30), default=None)
    weight: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    source_anchor_id: Mapped[str | None] = mapped_column(String(36), default=None)
    metadata_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(ISODateTime)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class UserConceptMastery(Base):
    """Concept Mastery 派生快照：每个 Concept 至多一条，唯一写入口 = Mastery Engine。

    只存 V1 真实使用字段；快照由有效 Quiz Evidence 全量重建，失败不影响上游事实。
    Concept 物理删除级联清理；状态归档保留快照但退出活跃聚合（查询层过滤）。
    """

    __tablename__ = "user_concept_mastery"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"))
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE"), unique=True
    )
    mastery_score: Mapped[float | None] = mapped_column(Float, default=None)
    mastery_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    positive_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    last_verified_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    algorithm_version: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
