"""跨课迁移领域服务（通用 Agent 第二阶段工单 04，spec 决策 17）。

记录内容与记录级资产（总结 / 知识点 / Todo / 复习资料）挂 record_id 天然随走；
原课程概念、历史作答（quiz 存量 concept_id / quiz_test_items / quiz_tests）、
学习证据（learning_events / learning_evidence，course_id 写入时固化＝历史归属）、
record_concepts 行零触碰（决策 18：读取期按记录所属课程过滤，移回即复现）。
事务内核心形态（HTTP 与 Agent 共用，create_core 先例）；掌握度不重算——
证据口径按历史归属不变，迁移不产生新的有效证据变化。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.schemas import CourseStatus
from app.modules.course.service import CourseService
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus
from app.modules.record.models import Record
from app.modules.record.service import RecordService
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException


class RecordMoveService:
    @staticmethod
    async def move_cross_course_core(
        session: AsyncSession, record: Record, target_course_id: str
    ) -> Record:
        """跨课迁移事务内核心（不得自行 begin）：目标课程存在且 ACTIVE、
        记录无进行中处理任务（等待处理完成再迁移）、目标非当前课程；修改
        record.course_id + 维护 updated_at + 同事务重建搜索索引（索引不含
        course 维度，重建是幂等纪律动作）。目标课程校验同 classification 口径
        （存在且 ACTIVE）。"""

        target_course = await CourseService.get(session, target_course_id)
        if target_course is None:
            raise CodedHTTPException(
                code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
            )
        if target_course.status != CourseStatus.ACTIVE:
            raise CodedHTTPException(
                code="COURSE_ARCHIVED", status_code=409, detail="已归档课程不能接受新资料"
            )
        if record.course_id == target_course_id:
            raise CodedHTTPException(
                code="RECORD_ALREADY_IN_COURSE",
                status_code=409,
                detail="记录已在该课程中，无需迁移",
            )
        active_job = await session.scalar(
            select(ProcessingJob.id).where(
                ProcessingJob.record_id == record.id,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
        )
        if active_job is not None:
            raise CodedHTTPException(
                code="RECORD_MOVE_JOB_IN_PROGRESS",
                status_code=409,
                detail="记录有正在进行的处理任务，请等待处理完成后再迁移",
            )
        record.course_id = target_course_id
        record.updated_at = utcnow()
        await session.flush()
        await SearchService.upsert_record_index(session, record.id)
        return record

    @staticmethod
    async def move_cross_course(
        session: AsyncSession, record_id: str, target_course_id: str
    ) -> Record:
        """HTTP 入口形态（None 语义不适用：记录不存在结构化 404）。"""
        async with session.begin():
            record = await RecordService.get(session, record_id)
            if record is None:
                raise CodedHTTPException(
                    code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
                )
            return await RecordMoveService.move_cross_course_core(session, record, target_course_id)
