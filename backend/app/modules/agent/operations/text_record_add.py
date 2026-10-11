"""add_text_record_to_course 操作注册项（通用 Agent 第一阶段工单 03）：复用验证锚点。

「向某课程添加这条记录」→ 模型经 search_courses 消歧固化 course_id → 薄工具创建
TEXT_RECORD_ADD 提案 → 用户确认卡确认（明示将尝试生成 AI 总结）→ 应用器在确认
事务内经文本捕获核心建记录（Record(SUMMARY_PENDING) + Transcript + 搜索索引 +
资料库回填 + APPLIED + result_json 原子提交）→ 事务内 best-effort 提交总结任务
（失败只记错误码，不回滚记录）。导入即注册；公共流程零改动（02 注册表原样复用）。
载荷契约（TextRecordAddPayload / TextRecordAddResult）见 agent/schemas.py。
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_dir import bound_data_dir
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    register_operation,
)
from app.modules.agent.schemas import TextRecordAddPayload, TextRecordAddResult
from app.modules.capture.schemas import CaptureType, TextCaptureCreate
from app.modules.capture.text_capture import TextCaptureService
from app.modules.library.schemas import ProposalType
from app.modules.summary.service import SummaryService

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
ADD_TEXT_RECORD_ACTION = "add_text_record_to_course"


async def apply_text_record_add(
    session: AsyncSession, payload: TextRecordAddPayload, _execution_id: str
) -> TextRecordAddResult:
    """TEXT_RECORD_ADD 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    经文本捕获事务内核心建记录（与 HTTP 路由共用，校验零双份漂移；课程不存在/
    归档在执行前重校验失败 → 提案 FAILED、零悬挂记录），随后在事务内 best-effort
    提交总结任务；返回类型化结果投影（记录 id + 总结任务真实状态），经注册表
    适配器校验后在确认事务内写进 result_json。
    """
    record_id = await TextCaptureService.create_core(
        session,
        TextCaptureCreate(
            capture_type=CaptureType.PASTE,
            content=payload.content,
            course_id=UUID(payload.course_id),
        ),
    )
    summary_job_id: str | None = None
    summary_error_code: str | None = None
    data_dir = bound_data_dir()
    if data_dir is not None:
        (
            summary_job_id,
            summary_error_code,
        ) = await SummaryService.enqueue_if_eligible_in_transaction(
            session,
            data_dir,
            record_id,
            log_event="text_record_add_summary_enqueue_failed",
            error_code="TEXT_RECORD_ADD_SUMMARY_ENQUEUE_FAILED",
        )
    return TextRecordAddResult(
        record_id=record_id,
        summary_job_id=summary_job_id,
        summary_error_code=summary_error_code,
    )


register_operation(
    OperationSpec(
        action=ADD_TEXT_RECORD_ACTION,
        proposal_type=ProposalType.TEXT_RECORD_ADD,
        level=OperationLevel.L1,
        payload_schema=TextRecordAddPayload,
        result_schema=TextRecordAddResult,
        applier=apply_text_record_add,
        undo_reason="创建类动作不在首批撤销范围，如需移除请在记录页手动删除",
    )
)
