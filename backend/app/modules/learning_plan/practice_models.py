"""要求修订为追加事实；准备结果保存原题版本摘要，供建卷时重新校验。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class PracticeRequirements(Base):
    __tablename__ = "practice_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    item_id: Mapped[str] = mapped_column(ForeignKey("learning_plan_items.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class PracticePreparation(Base):
    __tablename__ = "practice_preparations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    item_id: Mapped[str] = mapped_column(ForeignKey("learning_plan_items.id", ondelete="CASCADE"))
    requirements_id: Mapped[str] = mapped_column(
        ForeignKey("practice_requirements.id", ondelete="CASCADE")
    )
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    authority: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
