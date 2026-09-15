"""Course Brain 域 ORM（F4，ADR-0022）：课程级概念、概念关系与记录-概念出现索引。

concepts 无 deleted_at：ARCHIVED 即退役语义；CONFIRMED 概念的
(course_id, normalized_name) 唯一由迁移 0023 的部分唯一索引兜底。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class Concept(Base):
    """课程级规范概念：CANDIDATE 待审核 / CONFIRMED 正式 / ARCHIVED 退役。"""

    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"))
    canonical_name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    concept_type: Mapped[str] = mapped_column(String(30), default="TERM")
    importance: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="CANDIDATE")
    source: Mapped[str] = mapped_column(String(20), default="AI_EXTRACTED")
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class ConceptRelation(Base):
    """概念间有向关系（source → target）：AI 推断默认 CANDIDATE，需人工确认。"""

    __tablename__ = "concept_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"))
    source_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE")
    )
    target_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE")
    )
    relation_type: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="CANDIDATE")
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class RecordConcept(Base):
    """Concept 在某条记录中的出现；KP 来源经 knowledge_point_id 桥列接入。"""

    __tablename__ = "record_concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="CASCADE")
    )
    knowledge_point_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_points.id", ondelete="SET NULL"), default=None
    )
    relevance: Mapped[float] = mapped_column(Float, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    first_start_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
