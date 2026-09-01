from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.models.document import ProcessingJob
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.document import ProcessingJobStatus, ProcessingJobType
from app.schemas.record import RecordStatus
from app.services.course_service import CourseService
from app.services.record_service import RecordService

CLASSIFIABLE_STATUSES = frozenset({RecordStatus.NOTE, RecordStatus.SUMMARY_PENDING})
# 这些状态的重复升级只返回当前事实，不倒退状态、不创建 Job。
UPGRADE_REPEAT_STATUSES = frozenset(
    {
        RecordStatus.SUMMARY_PROCESSING,
        RecordStatus.SUMMARY_READY,
        RecordStatus.COMPLETED,
    }
)


async def _visible_record(session: AsyncSession, record_id: str) -> Record:
    record = await RecordService.get(session, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    return record


async def _require_active_course(session: AsyncSession, course_id: str) -> None:
    course = await CourseService.get(session, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在或已删除")
    if course.status != CourseStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="已归档课程不能接受新资料")


async def _require_transcript(session: AsyncSession, record_id: str) -> None:
    if await RecordService.get_transcript(session, record_id) is None:
        raise HTTPException(status_code=409, detail="Transcript 尚未生成")


async def _active_summary_job_id(
    session: AsyncSession,
    record_id: str,
) -> str | None:
    job_id = await session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.record_id == record_id,
            ProcessingJob.job_type == ProcessingJobType.SUMMARY,
            ProcessingJob.status.in_((ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)),
        )
    )
    return str(job_id) if job_id is not None else None


class RecordClassificationService:
    @staticmethod
    async def classify(
        session: AsyncSession,
        record_id: str,
        course_id: str,
    ) -> Record:
        async with session.begin():
            record = await _visible_record(session, record_id)
            await _require_active_course(session, course_id)
            if record.course_id != course_id:
                if record.course_id is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="学习记录已归到其他课程，本版本不支持重新归类",
                    )
                if record.status not in CLASSIFIABLE_STATUSES:
                    raise HTTPException(
                        status_code=409,
                        detail="当前状态不能归类，请等待内容处理完成或先处理失败记录",
                    )
                record.course_id = course_id
                record.updated_at = utcnow()
            await session.flush()
        return await _visible_record(session, record_id)

    @staticmethod
    async def upgrade(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_id: str,
        course_id: str | None,
    ) -> tuple[Record, str | None]:
        repeat_only = False
        async with session_factory() as session, session.begin():
            record = await _visible_record(session, record_id)
            if (
                course_id is not None
                and record.course_id is not None
                and record.course_id != course_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="学习记录已归到其他课程，本版本不支持重新归类",
                )
            if record.status in UPGRADE_REPEAT_STATUSES:
                repeat_only = True
            elif record.status in CLASSIFIABLE_STATUSES:
                if course_id is not None:
                    await _require_active_course(session, course_id)
                    if record.course_id is None:
                        record.course_id = course_id
                        record.updated_at = utcnow()
                elif record.course_id is None:
                    raise HTTPException(
                        status_code=422,
                        detail="UPGRADE_COURSE_REQUIRED：未归类记录升级前必须选择课程",
                    )
                else:
                    # 复用当前课程前重新校验，归档竞态不允许触发新的总结。
                    await _require_active_course(session, record.course_id)
                await _require_transcript(session, record_id)
                if record.status == RecordStatus.NOTE:
                    record.status = RecordStatus.SUMMARY_PENDING
                    record.updated_at = utcnow()
            else:
                raise HTTPException(
                    status_code=409,
                    detail="当前状态不能升级，请等待内容处理完成或先处理失败记录",
                )
            # 已有活动 Summary Job 是幂等事实：两路径都直接复用，不创建第二个 Job。
            active_job_id = await _active_summary_job_id(session, record_id)
            await session.flush()

        # 本地 Record/Transcript/课程归属已提交；Provider、同意或入队异常都不回滚整理结果。
        summary_job_id = active_job_id
        if not repeat_only and summary_job_id is None:
            from app.services.summary_service import SummaryService

            summary_job_id = await SummaryService.enqueue_if_eligible_best_effort(
                session_factory,
                data_dir,
                record_id,
                log_event="record_upgrade_summary_enqueue_failed",
                error_code="RECORD_UPGRADE_SUMMARY_ENQUEUE_FAILED",
            )
        async with session_factory() as session:
            latest = await _visible_record(session, record_id)
        return latest, summary_job_id
