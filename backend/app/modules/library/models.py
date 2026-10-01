"""library 域 ORM（library-rag-v1）：来源条目、条目-Record 关系、业务提案与学习者偏好。

LibraryItem 只表示用户拥有的原始来源；解析/分片/索引等技术状态不复制进本表，
由 service 从 processing_jobs 与 Segment 事实派生（可用性口径见 service 注释）。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class LibraryItem(Base):
    """原始资料条目：AUDIO / DOCUMENT / WEB / BOOK / TEXT；软删 30 天回收站（05）。"""

    __tablename__ = "library_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="SET NULL"), default=None
    )
    source_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    origin_uri: Mapped[str | None] = mapped_column(Text, default=None)
    local_path: Mapped[str | None] = mapped_column(Text, default=None)
    mime_type: Mapped[str | None] = mapped_column(String(100), default=None)
    file_size: Mapped[int | None] = mapped_column(Integer, default=None)
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class LibraryItemRecord(Base):
    """来源条目与 Record 的多对多事实：一书拆多章 / 多来源 Record 双向覆盖。"""

    __tablename__ = "library_item_records"

    library_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True
    )
    record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="PRIMARY")
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class CourseSharedRef(Base):
    """共享来源引用（工单 05）：course ↔ library_item 多对多，保归属复用。

    失效为查询期派生（条目软删即失效、恢复即复活），本表不存状态；条目物理
    删除 FK CASCADE 清理引用，归属迁移不触本表。
    """

    __tablename__ = "course_shared_refs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE")
    )
    library_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("library_items.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class AgentProposal(Base):
    """可跨重启审核的业务提案：创建不改事实，确认后由领域 Service 原子应用。"""

    __tablename__ = "agent_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    proposal_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    session_id: Mapped[str | None] = mapped_column(String(36), default=None)
    message_id: Mapped[str | None] = mapped_column(String(36), default=None)
    target_type: Mapped[str | None] = mapped_column(String(30), default=None)
    target_id: Mapped[str | None] = mapped_column(String(36), default=None)
    payload_json: Mapped[str] = mapped_column(Text)
    # 执行前快照（工单 03，spec 决策 12）：提交时后端同事务固化，确认卡预览、
    # 执行前重验与 Undo 补偿三用；旧提案（含存量 ORGANIZE）无快照＝NULL。
    snapshot_json: Mapped[str | None] = mapped_column(Text, default=None)
    evidence_refs_json: Mapped[str | None] = mapped_column(Text, default=None)
    # 操作回执（工单 02）：APPLIED 时由确认事务写入类型化结果，其余状态恒 NULL。
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    error_code: Mapped[str | None] = mapped_column(String(60), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class LearnerPreference(Base):
    """学习者偏好单例事实表（id 固定 me）：显式偏好用户直编，观察偏好仅经确认写入。"""

    __tablename__ = "learner_preferences"

    id: Mapped[str] = mapped_column(String(8), primary_key=True, default="me")
    user_selected_preference: Mapped[str] = mapped_column(Text, default="{}")
    observed_learning_preference: Mapped[str | None] = mapped_column(Text, default=None)
    observed_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_observed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
