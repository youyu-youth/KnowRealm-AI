from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

AssetType = Literal["summary", "knowledge_point", "quiz", "review_material"]


class RecentAssetOut(BaseModel):
    asset_type: AssetType
    record_id: str
    record_title: str
    course_id: str | None
    course_name: str | None
    asset_count: int
    asset_at: datetime
    time_basis: Literal["confirmed", "created"]
    href: str

    @field_serializer("asset_at")
    def serialize_time(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat().replace("+00:00", "Z")


class RecentAssetListOut(BaseModel):
    items: list[RecentAssetOut]
    total: int
    offset: int
    limit: int
