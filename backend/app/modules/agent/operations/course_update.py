"""update_course 操作注册项（通用 Agent 第二阶段工单 03）：首个修改类动作。

「把课程 X 改名为 Y」→ 模型经 search_courses 消歧固化 course_id → 薄工具创建
OP_COURSE_UPDATE 提案（提交时同事务固化执行前快照）→ 确认卡 before/after 预览 →
用户确认 → 应用器先执行前重验（快照比对，不匹配＝目标已变化失效），再经课程
更新事务内核心落库（与 HTTP 路由共用同一校验链）。快照一份三用：预览、重验、
Undo 补偿（spec 决策 12）。载荷契约见 agent/schemas.py。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    CourseArchivePayload,
    CourseStateSnapshot,
    CourseUpdatePayload,
    CourseUpdateResult,
)
from app.modules.course.schemas import (
    CourseType,
    CourseUpdate,
    EducationStage,
    LearningContext,
    LearningDepth,
)
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
UPDATE_COURSE_ACTION = "update_course"

# OP_COURSE_UPDATE 可修改字段（快照 before 投影与回执 after 投影的键集）。
COURSE_UPDATE_FIELDS = (
    "name",
    "learning_context",
    "education_stage",
    "depth",
    "course_type",
    "description",
)


async def capture_course_state(
    session: AsyncSession, payload: CourseUpdatePayload | CourseArchivePayload
) -> CourseStateSnapshot:
    """执行前快照读取器（course.* 三动作共用）：不存在/已软删 → 结构化拒绝。"""
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    # ORM 列是 str（Mapped[str]），快照字段以枚举声明——显式收窄与
    # pydantic 运行时 coerce 同口径（未知值＝坏数据，如实抛错）。
    return CourseStateSnapshot(
        updated_at=course.updated_at,
        name=course.name,
        status=course.status,
        learning_context=LearningContext(course.learning_context),
        education_stage=(
            EducationStage(course.education_stage) if course.education_stage else None
        ),
        depth=LearningDepth(course.depth) if course.depth else None,
        course_type=CourseType(course.course_type) if course.course_type else None,
        description=course.description,
    )


def resolve_course_target(
    payload: CourseUpdatePayload | CourseArchivePayload,
) -> tuple[str, str]:
    return "course", payload.course_id


async def apply_course_update(
    session: AsyncSession, proposal: AgentProposal
) -> CourseUpdateResult:
    """OP_COURSE_UPDATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验已由注册表适配器统一完成（快照比对）；此处经课程更新事务内核心
    落库（与 HTTP 路由共用校验链），返回被修改字段的 before / after 对照。
    """
    payload = parse_operation_payload(proposal, CourseUpdatePayload)
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    before = {field: getattr(course, field) for field in COURSE_UPDATE_FIELDS}
    # 工具面已滤 None（模型无法传递显式 null），payload 里的 None 恒＝未提供；
    # 值非 None 的字段才是本次要修改的字段（exclude_unset 在全字段序列化的
    # payload_json 反序列化后失真，按值过滤与工具面语义闭环）。
    provided = {
        key: value
        for key, value in payload.model_dump().items()
        if key != "course_id" and value is not None
    }
    await CourseService.update_core(session, course, CourseUpdate(**provided))
    after = {field: getattr(course, field) for field in COURSE_UPDATE_FIELDS}
    return CourseUpdateResult(
        course_id=payload.course_id,
        before={key: before[key] for key in before if before[key] != after[key]},
        after={key: after[key] for key in after if before[key] != after[key]},
    )


register_operation(
    OperationSpec(
        action=UPDATE_COURSE_ACTION,
        proposal_type=ProposalType.OP_COURSE_UPDATE,
        level=OperationLevel.L1,
        payload_schema=CourseUpdatePayload,
        result_schema=CourseUpdateResult,
        applier=apply_course_update,
        capture_state=capture_course_state,
        target_resolver=resolve_course_target,
    )
)
