from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.schemas import TextCaptureAccepted, TextCaptureCreate
from app.modules.course.schemas import CourseStatus
from app.modules.course.service import CourseService
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService
from app.modules.summary.service import SummaryService
from app.modules.transcript.models import Transcript
from app.shared.errors import CodedHTTPException

MAX_TEXT_BYTES = 1024 * 1024
TITLE_MAX_CHARS = 100

TEXT_CAPTURE_TYPES = {"QUICK_NOTE", "PASTE"}


def normalize_content(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")


def content_title(content: str) -> str:
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped[:TITLE_MAX_CHARS]
    return ""


class TextCaptureService:
    @staticmethod
    async def create(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        body: TextCaptureCreate,
    ) -> TextCaptureAccepted:
        if body.capture_type not in TEXT_CAPTURE_TYPES:
            raise CodedHTTPException(
                code="UNSUPPORTED_TEXT_CAPTURE",
                status_code=422,
                detail="UNSUPPORTED_TEXT_CAPTURE：仅支持速记或粘贴文本",
            )
        if body.course_id is not None and body.capture_type != "PASTE":
            raise CodedHTTPException(
                code="QUICK_NOTE_NO_COURSE",
                status_code=422,
                detail="QUICK_NOTE_NO_COURSE：速记不能选择课程",
            )
        content = normalize_content(body.content)
        if not content.strip():
            raise CodedHTTPException(
                code="EMPTY_TEXT", status_code=422, detail="EMPTY_TEXT：正文不能为空"
            )
        if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
            raise CodedHTTPException(
                code="TEXT_TOO_LARGE",
                status_code=422,
                detail="TEXT_TOO_LARGE：正文超过 1 MiB，请改用 TXT 或 MD 文档导入",
            )

        record_id = str(uuid4())
        now = utcnow()
        course_selected = body.course_id is not None
        async with session_factory() as session, session.begin():
            if course_selected:
                course = await CourseService.get(session, str(body.course_id))
                if course is None:
                    raise CodedHTTPException(
                        code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
                    )
                if course.status != CourseStatus.ACTIVE:
                    raise CodedHTTPException(
                        code="COURSE_ARCHIVED", status_code=409, detail="已归档课程不能接受新资料"
                    )
            session.add(
                Record(
                    id=record_id,
                    course_id=str(body.course_id) if course_selected else None,
                    capture_type=body.capture_type,
                    title=content_title(content),
                    status=(RecordStatus.SUMMARY_PENDING if course_selected else RecordStatus.NOTE),
                    duration_ms=0,
                    summary_confirmed_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()
            session.add(
                Transcript(
                    record_id=record_id,
                    language="und",
                    content=content,
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()
            await SearchService.upsert_record_index(session, record_id)

        summary_job_id: str | None = None
        if course_selected:
            summary_job_id = await SummaryService.enqueue_if_eligible_best_effort(
                session_factory,
                data_dir,
                record_id,
                log_event="text_capture_summary_enqueue_failed",
                error_code="TEXT_CAPTURE_SUMMARY_ENQUEUE_FAILED",
            )
        return TextCaptureAccepted(record_id=record_id, summary_job_id=summary_job_id)
