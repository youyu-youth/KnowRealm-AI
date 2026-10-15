from datetime import datetime
from typing import cast

from sqlalchemy import and_, case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.modules.course.models import Course
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import KnowledgePointGenerationStatus
from app.modules.quiz.models import Quiz
from app.modules.quiz.schemas import QuizGenerationStatus
from app.modules.record.models import Record
from app.modules.review_material.models import ReviewMaterial
from app.modules.review_material.schemas import ReviewMaterialStatus
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.today.asset_schemas import AssetType, RecentAssetListOut, RecentAssetOut

ASSET_TABS: dict[AssetType, str] = {
    "summary": "summary",
    "knowledge_point": "knowledge-points",
    "quiz": "quiz",
    "review_material": "review",
}


def _confirmed_rows(
    model: type[AiSummary] | type[ReviewMaterial], kind: AssetType
) -> Select[tuple[str, str, int, datetime, str]]:
    status = AiSummaryStatus.CONFIRMED if model is AiSummary else ReviewMaterialStatus.CONFIRMED
    ranked = (
        select(
            model.record_id,
            func.coalesce(model.confirmed_at, model.created_at).label("asset_at"),
            case((model.confirmed_at.is_not(None), "confirmed"), else_="created").label(
                "time_basis"
            ),
            func.row_number()
            .over(partition_by=model.record_id, order_by=(model.version_no.desc(), model.id))
            .label("position"),
        )
        .where(model.deleted_at.is_(None), model.status == status)
        .subquery()
    )
    return select(
        ranked.c.record_id,
        literal(kind).label("asset_type"),
        literal(1).label("asset_count"),
        ranked.c.asset_at,
        ranked.c.time_basis,
    ).where(ranked.c.position == 1)


def _active_rows(
    model: type[KnowledgePoint] | type[Quiz], kind: AssetType
) -> Select[tuple[str, str, int, datetime, str]]:
    status = (
        KnowledgePointGenerationStatus.ACTIVE
        if model is KnowledgePoint
        else QuizGenerationStatus.ACTIVE
    )
    return (
        select(
            model.record_id,
            literal(kind).label("asset_type"),
            func.count().label("asset_count"),
            func.max(model.created_at).label("asset_at"),
            literal("created").label("time_basis"),
        )
        .where(model.deleted_at.is_(None), model.generation_status == status)
        .group_by(model.record_id)
    )


class RecentAssetService:
    @staticmethod
    async def list_recent(
        session: AsyncSession,
        *,
        asset_type: AssetType | None = None,
        course_id: str | None = None,
        offset: int = 0,
        limit: int = 5,
    ) -> RecentAssetListOut:
        assets = union_all(
            _confirmed_rows(AiSummary, "summary"),
            _active_rows(KnowledgePoint, "knowledge_point"),
            _active_rows(Quiz, "quiz"),
            _confirmed_rows(ReviewMaterial, "review_material"),
        ).subquery()
        stmt = (
            select(
                assets,
                Record.title.label("record_title"),
                Record.course_id,
                Course.name.label("course_name"),
            )
            .join(Record, Record.id == assets.c.record_id)
            .outerjoin(Course, and_(Course.id == Record.course_id, Course.deleted_at.is_(None)))
            .where(
                Record.deleted_at.is_(None),
                or_(Record.course_id.is_(None), Course.id.is_not(None)),
            )
        )
        if asset_type is not None:
            stmt = stmt.where(assets.c.asset_type == asset_type)
        if course_id is not None:
            stmt = stmt.where(Record.course_id == course_id)
        total = cast(int, await session.scalar(select(func.count()).select_from(stmt.subquery())))
        rows = (
            await session.execute(
                stmt.order_by(assets.c.asset_at.desc(), assets.c.record_id, assets.c.asset_type)
                .offset(offset)
                .limit(limit)
            )
        ).mappings()
        items: list[RecentAssetOut] = []
        for row in rows:
            data = dict(row)
            kind = cast(AssetType, data["asset_type"])
            data["href"] = f"/records/{data['record_id']}?tab={ASSET_TABS[kind]}"
            items.append(RecentAssetOut.model_validate(data))
        return RecentAssetListOut(items=items, total=total, offset=offset, limit=limit)
