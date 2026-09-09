from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceAnchor(Base):
    """来源锚点：指向一个具体来源片段（分片 / 笔记 / 消息）的定位。

    Audio/Document 来源必须关联具体分片（迁移 CHECK 保证）；
    course_material_id 列预留（该表尚未存在，无外键）。
    """

    __tablename__ = "source_anchors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE")
    )
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(36))
    record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="CASCADE"), default=None
    )
    record_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("record_files.id", ondelete="CASCADE"), default=None
    )
    course_material_id: Mapped[str | None] = mapped_column(String(36), default=None)
    transcript_segment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("transcript_segments.id", ondelete="CASCADE"), default=None
    )
    document_segment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_segments.id", ondelete="CASCADE"), default=None
    )
    start_offset: Mapped[int | None] = mapped_column(Integer, default=None)
    end_offset: Mapped[int | None] = mapped_column(Integer, default=None)
    page_no: Mapped[int | None] = mapped_column(Integer, default=None)


class SourceAnchorLink(Base):
    """锚点链接：学习资产（summary/KP/quiz 等）与锚点的多态关联。"""

    __tablename__ = "source_anchor_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    resource_type: Mapped[str] = mapped_column(String(30))
    resource_id: Mapped[str] = mapped_column(String(36))
    source_anchor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_anchors.id", ondelete="CASCADE")
    )
    relation_type: Mapped[str] = mapped_column(String(20))
