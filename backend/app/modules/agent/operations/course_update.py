"""update_course 操作注册项（通用 Agent 第二阶段工单 03）：首个修改类动作。

「把课程 X 改名为 Y」→ 模型经 search_courses 消歧固化 course_id → 薄工具创建
OP_COURSE_UPDATE 提案（提交时同事务固化执行前快照）→ 确认卡 before/after 预览 →
用户确认 → 应用器先执行前重验（快照比对，不匹配＝目标已变化失效），再经课程
更新事务内核心落库（与 HTTP 路由共用同一校验链）。快照一份三用：预览、重验、
Undo 补偿（spec 决策 12）。载荷契约见 agent/schemas.py。

工单 06：本动作可撤销——补偿器 undo_update_course（恢复快照 before 值）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    UndoOperationResult,
    assert_undo_state,
    assert_undo_version,
    parse_undo_basis,
    register_operation,
)
from app.modules.agent.runs.models import AgentOperation
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
    session: AsyncSession, payload: CourseUpdatePayload, _execution_id: str
) -> CourseUpdateResult:
    """OP_COURSE_UPDATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验已由注册表适配器统一完成（快照比对）；此处经课程更新事务内核心
    落库（与 HTTP 路由共用校验链），返回被修改字段的 before / after 对照。
    """
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
        after={key: after[key] for key in before if before[key] != after[key]},
        after_updated_at=course.updated_at,
    )


async def undo_update_course(
    session: AsyncSession, original: AgentOperation
) -> UndoOperationResult:
    """update_course 补偿器（工单 06）：恢复原载荷修改字段的快照 before 值。

    撤销前重验：课程当前字段必须等于原操作执行后的预期态——payload 值覆盖
    快照对应字段（工具面滤 None，payload 非 None 字段＝原操作改过的字段），
    且 education_stage / depth 按 update_core 联动规则推导（任何 update 都会
    重算这对联动字段，执行后态恒为联动结果）。期间被手动改过 →
    OPERATION_UNDO_CONFLICT（不覆盖后续修改）。恢复＝payload 修改字段＋联动
    对写回快照值（快照本身是联动一致态，update_core 再联动一次幂等）。
    """
    payload, snapshot, result = parse_undo_basis(
        original, CourseUpdatePayload, CourseStateSnapshot, CourseUpdateResult
    )
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="OPERATION_UNDO_CONFLICT",
            status_code=409,
            detail="课程已不存在或已删除，无法撤销",
        )
    expected: dict[str, object] = {}
    for field in COURSE_UPDATE_FIELDS:
        value = getattr(payload, field)
        expected[field] = value if value is not None else getattr(snapshot, field)
    # 联动推导（与 update_core 同规则）：SCHOOL 保留 education_stage 清 depth，
    # 其余场景反之——原操作执行后这对字段必为联动结果。
    if expected["learning_context"] == LearningContext.SCHOOL:
        expected["depth"] = None
    else:
        expected["education_stage"] = None
    current = {field: getattr(course, field) for field in COURSE_UPDATE_FIELDS}
    assert_undo_state(dict(expected), current)
    assert_undo_version(result.after_updated_at, course.updated_at)
    provided = {
        field: getattr(snapshot, field)
        for field in COURSE_UPDATE_FIELDS
        if getattr(payload, field) is not None or field in ("education_stage", "depth")
    }
    await CourseService.update_core(session, course, CourseUpdate(**provided))
    return UndoOperationResult(restored=provided)


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
        undoer=undo_update_course,
    )
)
