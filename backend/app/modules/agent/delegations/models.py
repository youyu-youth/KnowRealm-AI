from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class AgentDelegation(Base):
    __tablename__ = "agent_delegations"
    __table_args__ = (UniqueConstraint("turn_id", "namespace", "logical_call_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("chat_turns.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(String(20), default="knowledge")
    contract_version: Mapped[int] = mapped_column(Integer, default=1)
    namespace: Mapped[str] = mapped_column(Text)
    logical_call_id: Mapped[str] = mapped_column(Text)
    args_fingerprint: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str] = mapped_column(ForeignKey("processing_jobs.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(Text, default=None)
    cancel_requested: Mapped[bool] = mapped_column(Integer, default=False)
    result_json: Mapped[str | None] = mapped_column(Text, default=None)
    error_code: Mapped[str | None] = mapped_column(Text, default=None)
    retry_request_id: Mapped[str | None] = mapped_column(Text, default=None)
    decision_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class DelegationDecision(Base):
    __tablename__ = "agent_delegation_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("chat_turns.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot_id: Mapped[str] = mapped_column(String(36), unique=True)
    decision_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
