"""ChatTurn 持久模型（切换会话不中断任务，票 01/02）。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class ChatTurn(Base):
    """一条用户输入对应的一次回答生成：受理原子落库，执行与观察分离。"""

    __tablename__ = "chat_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    user_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    request_id: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    cancel_requested: Mapped[bool] = mapped_column(Integer, default=False)
    execution_json: Mapped[str] = mapped_column(Text, default="{}")
    claim_token: Mapped[str | None] = mapped_column(String(36), default=None)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    output_revision: Mapped[int] = mapped_column(Integer, default=1)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    compacted_seq: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_json: Mapped[str | None] = mapped_column(Text, default=None)
    final_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), default=None
    )
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    # WAITING_USER 等待原因（票 02，JSON：kind/detail）；继续生成需要用户
    # 处理（恢复配置 / 同意 / 授权）或安全边界无法确定时写入。
    waiting_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class ChatTurnRun(Base):
    """控制归属：新直执行 Run 专属，复用 Run 共享，批准后独立 Run 不随轮次停止。"""

    __tablename__ = "chat_turn_runs"

    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True
    )
    control_scope: Mapped[str] = mapped_column(String(20))
    cancel_requested: Mapped[bool] = mapped_column(Integer, default=False)


class ChatTurnWait(Base):
    """稳定工具来源与原任务、框架 interrupt 的持久绑定；结果只记录一次。"""

    __tablename__ = "chat_turn_waits"
    __table_args__ = (UniqueConstraint("turn_id", "namespace", "logical_call_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(String(64))
    logical_call_id: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[str] = mapped_column(String(36))
    source_operation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_operations.id", ondelete="SET NULL"), default=None
    )
    interrupt_id: Mapped[str | None] = mapped_column(String(64), default=None)
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    execution_attempt: Mapped[int | None] = mapped_column(Integer, default=None)


class ChatTurnEvent(Base):
    """轮次持久事件：单调 seq（唯一），先同事务提交后通知 / 发送。"""

    __tablename__ = "chat_turn_events"
    __table_args__ = (UniqueConstraint("turn_id", "seq", name="idx_chat_turn_events_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    output_revision: Mapped[int] = mapped_column(Integer, default=1)
    type: Mapped[str] = mapped_column(String(20))
    segment_id: Mapped[str | None] = mapped_column(String(64), default=None)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), default=None)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class ChatTurnToolEffect(Base):
    """副作用逐项恢复记录（票 02，规格 §9）：来源键 + 参数指纹 + 可恢复结果。

    一次逻辑调用（namespace + logical_call_id）产生多项副作用时按 effect_index
    逐项记录；attempt 不进入来源键——重放/续跑命中已成功项直接复用原结构化
    结果，不再写入业务。同身份参数指纹变化拒绝执行。
    """

    __tablename__ = "chat_turn_tool_effects"
    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "namespace",
            "logical_call_id",
            "effect_index",
            name="idx_chat_turn_tool_effects_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(String(64))
    logical_call_id: Mapped[str] = mapped_column(String(64))
    effect_index: Mapped[int] = mapped_column(Integer, default=0)
    tool_name: Mapped[str] = mapped_column(String(64))
    args_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
