"""总结派生域共享判定（issue job-runner/01）。

quiz / knowledge_point / todo 三个生成域各自复制的 ``_summary_content`` 与
``_source_is_current``（以及 PREREQUISITE_CHANGED 取消理由）归一于此，消除
三处资格判定漂移；summary 域复用 ``summary_content`` 解析。
"""

from __future__ import annotations

import json
from typing import cast

from app.models.document import AiSummary
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.record.models import Record
from app.schemas.document import AiSummaryStatus
from app.schemas.summary import SummaryContent

PREREQUISITE_CHANGED = "PREREQUISITE_CHANGED"


def summary_content(summary: AiSummary) -> SummaryContent:
    """从 ai_summaries 行解析已确认总结的内容结构。"""
    payload = cast(dict[str, object], json.loads(summary.summary_json))
    return SummaryContent.model_validate(
        {
            "topic": summary.topic,
            "abstract": summary.abstract,
            "sections": payload.get("sections"),
        }
    )


def summary_source_is_current(
    record: Record | None,
    course: Course | None,
    summary: AiSummary | None,
    *,
    record_id: str,
) -> bool:
    """派生资格：记录与课程存活、课程 ACTIVE、总结仍属本记录且已确认。"""
    return bool(
        record is not None
        and record.deleted_at is None
        and course is not None
        and course.deleted_at is None
        and course.status == CourseStatus.ACTIVE
        and summary is not None
        and summary.record_id == record_id
        and summary.deleted_at is None
        and summary.status == AiSummaryStatus.CONFIRMED
    )
