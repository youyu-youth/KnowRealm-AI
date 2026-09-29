from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class LearningGoal(Base):
    """学习目标：挂单个知识空间，单空间同时至多一条 ACTIVE（部分唯一索引）。

    课程软删后目标随空间不可见（查询期 JOIN 过滤，不写级联），恢复课程即
    恢复；课程物理删除经 FK CASCADE 清理。
    """

    __tablename__ = "learning_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id", ondelete="CASCADE"))
    goal_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    target_date: Mapped[str | None] = mapped_column(String(10), default=None)
    daily_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    target_score: Mapped[float | None] = mapped_column(Float, default=None)
    scope_source: Mapped[str] = mapped_column(String(30))
    scope_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
