from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.chat import ChatMessage, ChatSession
from app.models.course import Course
from app.models.document import Transcript
from app.models.profile import PROFILE_ID, Profile
from app.models.record import Record
from app.schemas.chat import ChatMode, ChatRecordOption, ChatRole
from app.schemas.profile import PrimaryRole
from app.services.record_service import RecordService

ROLE_LABELS: dict[PrimaryRole, str] = {
    PrimaryRole.STUDENT: "学生",
    PrimaryRole.DEVELOPER: "程序员",
    PrimaryRole.OFFICE_WORKER: "职场人",
    PrimaryRole.OTHER: "其他",
}

NEUTRAL_PROFILE_SNAPSHOT = "你是 KnowRealm 学习助手。用户尚未建立档案，请以中性、通用的语气回答。"


def build_profile_snapshot(profile: Profile | None) -> str:
    """把角色与自我介绍固化为 SYSTEM 消息文本（会话创建时快照，档案后续修改不追溯）。"""
    if profile is None or profile.primary_role is None:
        return NEUTRAL_PROFILE_SNAPSHOT
    label = ROLE_LABELS[profile.primary_role]
    if profile.about_me:
        return f"你是 KnowRealm 学习助手。用户角色：{label}。用户自我介绍：{profile.about_me}"
    return f"你是 KnowRealm 学习助手。用户角色：{label}。"


class ChatSessionService:
    @staticmethod
    async def record_options(session: AsyncSession) -> list[ChatRecordOption]:
        rows = await session.execute(
            select(
                Record.id,
                Record.title,
                Record.course_id,
                Transcript.id.is_not(None).label("has_transcript"),
            )
            .outerjoin(Course, Course.id == Record.course_id)
            .outerjoin(
                Transcript,
                and_(
                    Transcript.record_id == Record.id,
                    Transcript.deleted_at.is_(None),
                ),
            )
            .where(
                Record.deleted_at.is_(None),
                or_(
                    Record.course_id.is_(None),
                    and_(Course.id.is_not(None), Course.deleted_at.is_(None)),
                ),
            )
            .order_by(Record.created_at.desc(), Record.id.desc())
        )
        return [ChatRecordOption.model_validate(row) for row in rows.mappings()]

    @staticmethod
    async def create(session: AsyncSession, *, record_id: str | None = None) -> ChatSession:
        async with session.begin():
            record = None
            if record_id is not None:
                record = await RecordService.get(session, record_id)
                if record is None:
                    raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
                if await RecordService.get_transcript(session, record_id) is None:
                    raise HTTPException(
                        status_code=409, detail="TRANSCRIPT_NOT_READY：转写尚未生成，暂不可挂载"
                    )
            now = utcnow()
            chat = ChatSession(
                id=str(uuid4()),
                course_id=record.course_id if record is not None else None,
                record_id=record_id,
                concept_id=None,
                mode=ChatMode.ASK,
                title=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            session.add(chat)
            await session.flush()
            if record is None:
                profile = await session.get(Profile, PROFILE_ID)
                session.add(
                    ChatMessage(
                        id=str(uuid4()),
                        session_id=chat.id,
                        role=ChatRole.SYSTEM,
                        content=build_profile_snapshot(profile),
                        citations_json=None,
                        model=None,
                        token_usage_json=None,
                        created_at=now,
                    )
                )
            await session.flush()
            return chat

    @staticmethod
    async def list(session: AsyncSession) -> list[ChatSession]:
        return list(
            (
                await session.scalars(
                    select(ChatSession)
                    .where(ChatSession.deleted_at.is_(None))
                    .order_by(ChatSession.updated_at.desc())
                )
            ).all()
        )

    @staticmethod
    async def get(session: AsyncSession, session_id: str) -> ChatSession | None:
        chat = await session.get(ChatSession, session_id)
        if chat is None or chat.deleted_at is not None:
            return None
        return chat

    @staticmethod
    async def rename(session: AsyncSession, session_id: str, title: str) -> ChatSession | None:
        async with session.begin():
            chat = await ChatSessionService.get(session, session_id)
            if chat is None:
                return None
            # 重命名只改展示标题，不推进 updated_at：列表"最近更新"语义 = 会话活跃度（消息往来）。
            chat.title = title
            await session.flush()
            return chat

    @staticmethod
    async def soft_delete(session: AsyncSession, session_id: str) -> bool:
        async with session.begin():
            chat = await ChatSessionService.get(session, session_id)
            if chat is None:
                return False
            now = utcnow()
            chat.deleted_at = now
            chat.updated_at = now
        return True
