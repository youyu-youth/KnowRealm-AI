"""来源锚点服务：锚点读写唯一入口（写入者首个 = 对话转学习资产 V1）。"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.record.models import Record
from app.modules.source_anchor.models import SourceAnchor, SourceAnchorLink
from app.modules.source_anchor.schemas import SourceAnchorOut
from app.shared.errors import CodedHTTPException

ResourceType = Literal[
    "SUMMARY", "KNOWLEDGE_POINT", "QUIZ", "MISCONCEPTION", "CHAT_MESSAGE", "RECORD_ANALYSIS"
]
RelationType = Literal["SUPPORTS", "PRIMARY", "CONTRADICTS", "REFERENCES"]


class SourceAnchorService:
    @staticmethod
    async def list_by_record(session: AsyncSession, record_id: str) -> list[SourceAnchorOut]:
        record = (
            await session.scalars(
                select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
            )
        ).one_or_none()
        if record is None:
            raise CodedHTTPException(
                code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
            )
        anchors = (
            await session.scalars(
                # 按主键排序仅为响应确定性；锚点无时间/序号列可依。
                select(SourceAnchor)
                .where(SourceAnchor.record_id == record_id)
                .order_by(SourceAnchor.id)
            )
        ).all()
        return [SourceAnchorOut.model_validate(anchor) for anchor in anchors]

    @staticmethod
    async def create_chat_message_anchor(
        session: AsyncSession,
        *,
        course_id: str,
        chat_message_id: str,
        record_id: str,
    ) -> SourceAnchor:
        """写入 CHAT_MESSAGE 锚点（对话转知识点，锚点体系首个写入者）。

        无独立事务：必须由调用方的业务事务包住（对齐 learning.events 同事务
        红线），保证知识点、搜索索引、锚点、链接要么同生要么同灭。
        """
        anchor = SourceAnchor(
            course_id=course_id,
            source_type="CHAT_MESSAGE",
            source_id=chat_message_id,
            record_id=record_id,
        )
        session.add(anchor)
        await session.flush()
        return anchor

    @staticmethod
    async def link_resource(
        session: AsyncSession,
        *,
        resource_type: ResourceType,
        resource_id: str,
        source_anchor_id: str,
        relation_type: RelationType,
    ) -> SourceAnchorLink:
        """锚点 ↔ 学习资产链接；重复四元组由表上 UNIQUE 约束兜底。

        同 create_chat_message_anchor：无独立事务，由调用方事务包住。
        """
        link = SourceAnchorLink(
            resource_type=resource_type,
            resource_id=resource_id,
            source_anchor_id=source_anchor_id,
            relation_type=relation_type,
        )
        session.add(link)
        await session.flush()
        return link
