from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="CASCADE"), unique=True
    )
    language: Mapped[str] = mapped_column(String(35))
    content: Mapped[str] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer, default=1)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class TranscriptSegment(Base):
    """句级转写分片：transcripts.content 的派生定位层（F1，数据模型 v2.5）。

    四个时间戳列允许 NULL——全库唯一退化态（无时间轴来源：存量回填 /
    in-flight 降级 / 编辑未命中句共用该语义）；speaker 列恒 NULL 预留。
    """

    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE")
    )
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("record_files.id", ondelete="CASCADE")
    )
    sequence_no: Mapped[int] = mapped_column(Integer)
    record_start_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    record_end_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    file_start_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    file_end_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    speaker: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)


class DocumentSegment(Base):
    """文档分片：record_file（导入文档）或 library_item（资料来源）的内容切块。

    library_item_id 为资料来源直挂分片（0026 起 FK）；本期 record_id 路径之外
    的挂靠恒 NULL。course_id 随挂靠记录所属课程（收件箱记录为 NULL）。
    """

    __tablename__ = "document_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), default=None
    )
    record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="CASCADE"), default=None
    )
    record_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("record_files.id", ondelete="CASCADE"), default=None
    )
    library_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("library_items.id", ondelete="CASCADE"), default=None
    )
    sequence_no: Mapped[int] = mapped_column(Integer)
    page_no: Mapped[int | None] = mapped_column(Integer, default=None)
    section_title: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int | None] = mapped_column(Integer, default=None)
    end_offset: Mapped[int | None] = mapped_column(Integer, default=None)
    content_hash: Mapped[str] = mapped_column(Text)
