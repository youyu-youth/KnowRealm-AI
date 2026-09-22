"""执行事实三表 ORM 模型（迁移 0030，spec 决策 2/3/22）。

- AgentRun：批次执行单元。session_id 仅溯源（无 FK——删除聊天会话不删除
  任务历史，spec 决策 22）；WAITING_JOB 为第三阶段预留枚举、本阶段无写入者。
- AgentOperation：执行事实唯一源。单步操作 run_id 空；不持久化 RUNNING
  （每个操作一个原子事务，崩溃=未发生）；undo_of / undone_by 自引用为
  Undo 补偿链（工单 06 消费）。
- AgentActivity：审计流（模式切换；本阶段无写入者，02 票接入）。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str | None] = mapped_column(String(36), default=None)
    auth_mode: Mapped[str] = mapped_column(String(20))
    instruction_text: Mapped[str | None] = mapped_column(Text, default=None)
    proposal_id: Mapped[str | None] = mapped_column(String(36), default=None)
    status: Mapped[str] = mapped_column(String(20))
    plan_json: Mapped[str | None] = mapped_column(Text, default=None)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    waiting_reason: Mapped[str | None] = mapped_column(Text, default=None)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class AgentOperation(Base):
    __tablename__ = "agent_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), default=None
    )
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_proposals.id"), default=None
    )
    action: Mapped[str] = mapped_column(String(60))
    level: Mapped[str] = mapped_column(String(4))
    target_type: Mapped[str | None] = mapped_column(String(30), default=None)
    target_id: Mapped[str | None] = mapped_column(String(36), default=None)
    payload_json: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str | None] = mapped_column(Text, default=None)
    authorization_json: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    attempts_json: Mapped[str | None] = mapped_column(Text, default=None)
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    error_code: Mapped[str | None] = mapped_column(String(60), default=None)
    undo_of: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_operations.id", ondelete="SET NULL"), default=None
    )
    undone_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_operations.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class AgentActivity(Base):
    __tablename__ = "agent_activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    activity_type: Mapped[str] = mapped_column(String(30))
    from_mode: Mapped[str] = mapped_column(String(20))
    to_mode: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(10))
    session_id: Mapped[str | None] = mapped_column(String(36), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
