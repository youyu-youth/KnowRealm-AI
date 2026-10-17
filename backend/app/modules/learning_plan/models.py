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


class LearningPlan(Base):
    """学习计划版本：挂学习目标，(goal_id, plan_version) 唯一、同目标同时至多
    一条 ACTIVE（部分唯一索引）。effective_from = 确认落库日；换代 / 完结时由
    Service 写 effective_to（重生成随工单 03 启用）。
    """

    __tablename__ = "learning_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    goal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_goals.id", ondelete="CASCADE")
    )
    plan_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    effective_from: Mapped[str] = mapped_column(String(10))
    effective_to: Mapped[str | None] = mapped_column(String(10), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class LearningPlanItem(Base):
    """计划项：四类动作按日排期；reason_json 存逐项生成理由；user_locked 由
    Service 在用户手动编辑时置 true（重生成原样保留，工单 03）。completed_at
    仅 DONE 时写入（学习时长统计口径，不进学习证据链）；跳过不写。

    record_id / concept_id 物理删除置空（软删由查询期过滤，与 Record 同模式）。
    """

    __tablename__ = "learning_plan_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_plans.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="SET NULL"), default=None
    )
    concept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("concepts.id", ondelete="SET NULL"), default=None
    )
    phase_title: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    scheduled_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    user_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    study_visit_id: Mapped[str | None] = mapped_column(String(36), default=None)
    # 保留启动时身份，来源物理删除后仍能解释本次访问失效。
    study_record_id: Mapped[str | None] = mapped_column(String(36), default=None)
    study_started_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    study_tab: Mapped[str] = mapped_column(String(30), default="summary")
    reason_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
