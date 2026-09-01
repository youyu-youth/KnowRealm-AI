from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
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


class AiSummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    transcript_source_version: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    token_usage_json: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    user_feedback: Mapped[str | None] = mapped_column(Text, default=None)
    confirmed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_jobs.id", ondelete="SET NULL"), default=None
    )
    name: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float)
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    generation_status: Mapped[str] = mapped_column(String(20))
    source_anchor_id: Mapped[str | None] = mapped_column(String(36), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_jobs.id", ondelete="SET NULL"), default=None
    )
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    generation_status: Mapped[str] = mapped_column(String(20))
    question_type: Mapped[str] = mapped_column(String(20))
    stem: Mapped[str] = mapped_column(String(500))
    options_json: Mapped[str] = mapped_column(Text)
    correct_answer_json: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(10))
    user_answer_json: Mapped[str | None] = mapped_column(Text, default=None)
    answer_result: Mapped[str | None] = mapped_column(String(10), default=None)
    answered_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class QuizTest(Base):
    __tablename__ = "quiz_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"))
    record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("records.id"), default=None
    )
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float, default=None)
    started_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class QuizTestItem(Base):
    __tablename__ = "quiz_test_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    test_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_tests.id", ondelete="CASCADE")
    )
    quiz_id: Mapped[str] = mapped_column(String(36), ForeignKey("quizzes.id"))
    sequence_no: Mapped[int] = mapped_column(Integer)
    user_answer_json: Mapped[str | None] = mapped_column(Text, default=None)
    result: Mapped[str | None] = mapped_column(String(10), default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    ai_grade_json: Mapped[str | None] = mapped_column(Text, default=None)
    answered_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_jobs.id", ondelete="SET NULL"), default=None
    )
    content: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10))
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    generation_status: Mapped[str | None] = mapped_column(String(20), default=None)
    sort_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
