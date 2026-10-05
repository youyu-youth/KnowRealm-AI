"""generate_plan_draft 操作注册项与 PLAN_DRAFT job worker（工单 07，M2）。

多资料建课 Run 的「计划生成意图」末步：应用器提交 PLAN_DRAFT 后台任务
（LLM 草案生成不占推进事务），Run 转 WAITING_JOB；job worker 复用
PlanGenerationService 生成结构化草案（确定性排期由 pack_schedule 承担），
完成时在写回事务内落 OP_PLAN_CONFIRM 草案确认卡——**草案确认是 Run 之外
的人工闸门**（spec M2：不算 Run 步骤），用户经既有确认卡流程确认后计划
才落库，总结与学习资产原有采纳审核不被批次授权跳过。

L2（计划头 + 批量项创建前置，与 confirm_plan 同级）；不在撤销范围（草案
未落库，确认前关闭即弃）。goal_id 可经计划引用注入（建目标步骤输出），
引用解析与快照现固化由推进 worker 既有机制承担。
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.operations.plan_confirm import (
    capture_plan_confirm_state,
    require_active_goal,
    validate_plan_confirm_submission,
)
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.schemas import (
    PlanConfirmPayload,
    PlanConfirmStateSnapshot,
    PlanDraftGeneratePayload,
    PlanDraftGenerateResult,
)
from app.modules.course.service import CourseService
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.learning_plan.generation import PlanGenerationOutcome, PlanGenerationService
from app.modules.learning_plan.scheduling import ScheduleInfeasible, local_today
from app.modules.learning_plan.service import GoalService, PlanService
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.modules.llm.service import StructuredGenerationError
from app.modules.settings.config import load_llm_provider
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

# 动作标识（= 注册表 action；计划项动作枚举 GENERATE_PLAN_DRAFT 的映射值）。
GENERATE_PLAN_DRAFT_ACTION = "generate_plan_draft"

# PLAN_DRAFT job 的稳定失败码（error_code 列无 CHECK，登记前端翻译即可）：
# LLM 未配置 / 目标不可用（执行期被完结或归档）/ 课程无资料（SUGGESTIONS 路径）。
PLAN_DRAFT_LLM_UNCONFIGURED = "PLAN_DRAFT_LLM_UNCONFIGURED"
PLAN_DRAFT_GOAL_UNAVAILABLE = "PLAN_DRAFT_GOAL_UNAVAILABLE"
PLAN_DRAFT_NO_MATERIALS = "PLAN_DRAFT_NO_MATERIALS"


async def apply_plan_draft_generate(
    session: AsyncSession, proposal: AgentProposal
) -> PlanDraftGenerateResult:
    """OP_PLAN_DRAFT 应用器（调用方事务内）：提交草案生成任务即成功
    （result 留回执），真实生成由 job worker 异步完成。

    提交前状态依赖由 capture_state 承担（既有目标：目标不可达 / 非进行中 /
    已有进行中计划零提交）；goal_id 经引用注入时目标在同批前序步骤创建，
    快照跳过、由推进 worker 现固化，状态依赖兜底在学习侧（ACTIVE 校验与
    部分唯一索引）。operation_id 进 job input：写回时反查 run 会话归属，
    草案确认卡落进触发 Run 的会话（弃置语义同口径）。
    """
    payload = parse_operation_payload(proposal, PlanDraftGeneratePayload)
    job_id = str(uuid4())
    now = utcnow()
    session.add(
        ProcessingJob(
            id=job_id,
            record_id=None,
            job_type=ProcessingJobType.PLAN_DRAFT,
            status=ProcessingJobStatus.PENDING,
            progress=0,
            attempts=0,
            # 业务失败（LLM 未配置 / 无资料 / 排期不可行）仍一次性终态；3 次
            # 预算只被重启恢复消费（进程中断自动重投，工单 08）。
            max_attempts=3,
            input_json=json.dumps(
                {"goal_id": payload.goal_id, "operation_id": proposal.id},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return PlanDraftGenerateResult(awaited_job_id=job_id)


async def capture_plan_draft_state(
    session: AsyncSession, payload: PlanDraftGeneratePayload
) -> PlanConfirmStateSnapshot:
    """执行前快照（既有目标路径）：目标态 + 排期约束字段——执行前目标被改
    （期限 / 每日投入变化会让草案失真）→ 快照比对失效。状态依赖（非进行中 /
    已有进行中计划）在此结构化拒绝；course_name 供 Run 卡与审计定位。"""
    goal = await require_active_goal(session, payload.goal_id)
    await PlanService.require_no_active(session, goal.id)
    course = await CourseService.get(session, goal.course_id)
    return PlanConfirmStateSnapshot(
        updated_at=goal.updated_at,
        title=goal.title,
        target_date=(
            date.fromisoformat(goal.target_date) if goal.target_date is not None else None
        ),
        daily_minutes=goal.daily_minutes,
        course_name=course.name if course is not None else goal.course_id,
    )


def resolve_plan_draft_target(payload: PlanDraftGeneratePayload) -> tuple[str, str]:
    return "goal", payload.goal_id


# ---------------------------------------------------------------------------
# PLAN_DRAFT job worker（LLM 草案生成 → 草案确认卡）


@dataclass(frozen=True)
class ClaimedPlanDraft(ClaimedJob):
    """草案生成任务坐标：goal 是业务主体（record_id 坐标位空串，先例见
    AGENT_RUN 的 run_id 坐标位）。"""

    goal_id: str
    operation_id: str


class PlanDraftGoalUnavailable(Exception):
    """目标不可用（不存在 / 已完结 / 已有进行中计划）：job 落稳定失败码，
    Run 等待步骤翻 FAILED 后可单独重试。"""


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == ProcessingJobType.PLAN_DRAFT,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                (ProcessingJob.next_run_at.is_(None) | (ProcessingJob.next_run_at <= now)),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    _preflight: None,
) -> ClaimCheck[ClaimedPlanDraft]:
    input_data: object = json.loads(job.input_json)
    goal_id = (
        cast(dict[str, object], input_data).get("goal_id") if isinstance(input_data, dict) else None
    )
    operation_id = (
        cast(dict[str, object], input_data).get("operation_id")
        if isinstance(input_data, dict)
        else None
    )
    if not isinstance(goal_id, str) or not isinstance(operation_id, str):
        return CancelClaim("plan_draft_input_invalid")
    return Ready(
        ClaimedPlanDraft(job_id=job.id, record_id="", goal_id=goal_id, operation_id=operation_id)
    )


async def execute(
    ctx: ClaimedPlanDraft,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> object:
    """领取后二次确认仍 RUNNING，再提取生成上下文（LLM 调用期间零连接）。

    返回值交 writeback 落草案确认卡；目标不可用抛 PlanDraftGoalUnavailable
    （job 落稳定失败码，等待步骤翻 FAILED 可重试）。生成完成后重验排期
    一致性——生成期间的约束 / 目标态变化在此拦截，旧口径草案不落确认卡。"""
    async with session_factory() as session:
        active_job = (
            await session.execute(
                select(ProcessingJob.id).where(
                    ProcessingJob.id == ctx.job_id,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                )
            )
        ).scalar_one_or_none()
        if active_job is None:
            return None
        goal = await GoalService.get(session, ctx.goal_id)
        if goal is None or goal.status != "ACTIVE":
            raise PlanDraftGoalUnavailable("goal_not_active")
        await PlanService.require_no_active(session, goal.id)
        materials = await PlanGenerationService.gather_materials(session, goal.course_id)
        evidence = await PlanGenerationService.retrieve_evidence(
            session, goal.course_id, goal.title
        )
    provider = load_llm_provider(data_dir)
    if provider is None or not provider.api_key:
        raise CodedHTTPException(
            code=PLAN_DRAFT_LLM_UNCONFIGURED,
            status_code=409,
            detail="尚未配置 LLM 供应商，无法生成学习计划草案",
        )
    outcome = await PlanGenerationService.generate(
        session_factory=session_factory,
        goal=goal,
        provider=provider,
        today=local_today(),
        materials=materials,
        evidence=evidence,
    )
    if outcome.kind != "DRAFT":
        # 课程无资料（SUGGESTIONS）：不如实静默成功——指引已承诺任务完成后产
        # 草案卡，此路径落稳定失败码交等待步骤翻 FAILED（Run 部分完成、补资料
        # 后可单独重试），建议内容由模型在对话转述（工单 07 review）。
        raise CodedHTTPException(
            code=PLAN_DRAFT_NO_MATERIALS,
            status_code=409,
            detail="课程还没有资料，无法生成学习计划草案，请先补充资料后重试",
        )
    assert outcome.plan is not None
    # 生成期间（LLM 秒~分钟窗口）目标约束或状态可能已变：写回的确认卡快照
    # 在 writeback 时点采集，会把这期间的变化洗白进快照、旧口径草案经确认
    # 落库（如每日预算 60→15 后同日仍落 90 分钟）。提交前重验（与工具路径
    # 同款提交时执法：重读最新目标重算排期比对）——不一致即稳定失败码，
    # job 落 FAILED 可单独重试，重试以新约束重新生成（07 review 五轮 P2）。
    async with session_factory() as session:
        await validate_plan_confirm_submission(
            session,
            PlanConfirmPayload(goal_id=ctx.goal_id, phases=outcome.plan.phases),
        )
    return outcome


async def writeback(
    ctx: ClaimedPlanDraft,
    outcome: object,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """写回事务：job SUCCEEDED；草案路径同事务落 OP_PLAN_CONFIRM 草案确认卡
    （落卡前事务内终验排期一致性，快照同口径固化——确认时既有重验与弃置
    语义零改动复用）。

    草案确认卡归属触发 Run 的会话（经 operation_id → run 反查）：弃置语义
    （话题翻篇批量置 REJECTED）与工具路径同口径。无资料路径（SUGGESTIONS）
    在 execute 即落稳定失败码，不会到达这里。"""
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        now = utcnow()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.next_run_at = None
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
        result: dict[str, object] = {"goal_id": ctx.goal_id}
        if isinstance(outcome, PlanGenerationOutcome):
            plan = outcome.plan
            assert plan is not None
            operation = await session.get(AgentOperation, ctx.operation_id)
            run = await session.get(AgentRun, operation.run_id) if operation is not None else None
            payload = PlanConfirmPayload(goal_id=ctx.goal_id, phases=plan.phases)
            # 写回事务内终验（07 review 九轮 P2）：execute 尾部校验与写回之间存在
            # 窗口，期间约束再变会被写回时点的新快照洗白——与 capture 同事务
            # 重验排期一致性，变化原子拦截（异常回滚整个写回，job 走失败链）。
            await validate_plan_confirm_submission(session, payload)
            snapshot = await capture_plan_confirm_state(session, payload)
            proposal = await ProposalService.create_core(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.OP_PLAN_CONFIRM,
                    payload=payload.model_dump(mode="json"),
                    session_id=run.session_id if run is not None else None,
                    message_id=None,
                ),
                snapshot_json=snapshot.model_dump_json(),
            )
            result["proposal_id"] = proposal.id
            result["item_count"] = sum(len(phase.items) for phase in plan.phases)
            logger.info(
                "plan_draft_proposal_created",
                goal_id=ctx.goal_id,
                proposal_id=proposal.id,
                run_id=run.id if run is not None else None,
            )
        job.result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return True


def failure_code(_ctx: ClaimedPlanDraft, exc: Exception) -> str | None:
    if isinstance(exc, PlanDraftGoalUnavailable):
        return PLAN_DRAFT_GOAL_UNAVAILABLE
    if isinstance(exc, ScheduleInfeasible):
        # 目标约束铺不开（期限容量 / 单项超预算）：与工具路径同码，重试不自愈
        # （约束未变），用户需调整目标后重试（工单 07 review）。
        return "PLAN_SCHEDULE_INFEASIBLE"
    if isinstance(exc, CodedHTTPException):
        return exc.code
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    ctx: ClaimedPlanDraft,
    session: AsyncSession,
    job: ProcessingJob,
    _record: object,
    error_code: str,
    now: datetime,
) -> bool:
    mark_failed(job, code=error_code, message="学习计划草案生成失败", now=now)
    return True


def plan_draft_spec(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
    data_dir: Path,
) -> WorkerSpec[None, ClaimedPlanDraft, object]:
    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="plan_draft_unexpected_failure", error_code="INTERNAL_ERROR")

    async def recover() -> None:
        """重启恢复（工单 08）：进程中断 ≠ 业务失败——attempts 预算内回
        PENDING 自动重投（对齐 document_worker.recover_running 形态），等待
        中的 Run 经领取核对自动接续；预算耗尽才翻终态 FAILED
        （WORKER_INTERRUPTED），等待步骤走失败分流、可手动重试。无 record
        主体（goal 坐标在 input_json），零 Record 联动与 notify。"""
        now = utcnow()
        async with session_factory() as session, session.begin():
            jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob).where(
                            ProcessingJob.job_type == ProcessingJobType.PLAN_DRAFT,
                            ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        )
                    )
                ).all()
            )
            for job in jobs:
                if job.attempts < job.max_attempts:
                    job.status = ProcessingJobStatus.PENDING
                    job.next_run_at = now + timedelta(seconds=2 ** max(job.attempts, 0))
                else:
                    job.status = ProcessingJobStatus.FAILED
                    job.finished_at = now
                job.error_code = "WORKER_INTERRUPTED"
                job.error_message = "学习计划草案生成被意外中断"
                job.updated_at = now

    return WorkerSpec(
        name="plan_draft_worker",
        job_type=ProcessingJobType.PLAN_DRAFT,
        poll_interval=1.0,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, data_dir),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
    )


register_operation(
    OperationSpec(
        action=GENERATE_PLAN_DRAFT_ACTION,
        proposal_type=ProposalType.OP_PLAN_DRAFT,
        level=OperationLevel.L2,
        payload_schema=PlanDraftGeneratePayload,
        result_schema=PlanDraftGenerateResult,
        applier=apply_plan_draft_generate,
        capture_state=capture_plan_draft_state,
        target_resolver=resolve_plan_draft_target,
        undo_reason="草案未落库（确认前关闭即弃），无需撤销；确认后的计划调整用既有计划工具",
        waits_for_job=True,
    )
)
