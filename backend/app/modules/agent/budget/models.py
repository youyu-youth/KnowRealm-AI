"""准入与实际输出事实；不保存参数和结果正文。"""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BudgetCall(Base):
    __tablename__ = "chat_turn_budget_calls"
    __table_args__ = (UniqueConstraint("turn_id", "namespace", "logical_call_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(String(64))
    logical_call_id: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(64))
    args_fingerprint: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[int] = mapped_column(Integer)
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_delegations.id"), default=None
    )


class BudgetOutput(Base):
    __tablename__ = "chat_turn_budget_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    call_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turn_budget_calls.id", ondelete="CASCADE"), index=True
    )
    chars_fed: Mapped[int] = mapped_column(Integer)
