"""来源锚点服务：锚点读写唯一入口（本期仅读侧，写入者=后续 A1/A3/graph 票）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.record.models import Record
from app.modules.source_anchor.models import SourceAnchor
from app.modules.source_anchor.schemas import SourceAnchorOut
from app.shared.errors import CodedHTTPException


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
