"""批量整理计划工具（通用 Agent 第二阶段工单 05，spec 决策 10/13）。

工具语义恒为「完成这批整理」：是否需要整卡确认（计划卡）由后端按授权档位与
阈值判定，工具名称与描述不随档位改变（spec 用户故事 39）——请求批准档与超
阈值时落 OP_BATCH 计划卡等整卡一次确认，帮我批准档阈值内 / 完全访问档直建
Run 并给批次回执。

参数 schema 是本工具的宽松声明（各字段可省；未知键透传给载荷判别），真实执法
在计划载荷（runs.schemas.BatchPlanPayload）与逐项动作判别 schema（操作注册表）
于提交时完成：缺项 / 非法动作 / 非法参数一律结构化返回，由模型转述或追问。
"""

import json
from typing import Any, cast

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.modules.agent.runs.plans import submit_batch_plan
from app.modules.agent.runtime import current_agent_runtime

# 工具名（langchain @tool 注册名 = 函数名）。
PLAN_BATCH_OPERATIONS_TOOL_NAME = "plan_batch_operations"


class BatchPlanItemArgs(BaseModel):
    """计划项（宽松声明：缺失 / 未知项由载荷判别在提交时结构化拒绝）。"""

    model_config = ConfigDict(extra="allow")

    action: str | None = Field(
        default=None,
        description=(
            "条目动作：update_library_item（改标题 / 归类）、archive_library_item"
            "（归档）、create_course（新建课程）、ingest_library_item（导入网页资料）"
        ),
    )
    item_id: str | None = Field(
        default=None,
        description="目标资料条目 id（update / archive 必填，先用 search_library 查找消歧取得）",
    )
    title: str | None = Field(
        default=None, description="条目标题（update 改名 / ingest 缺省用域名）"
    )
    course_id: str | dict[str, Any] | None = Field(
        default=None,
        description=(
            "归类目标课程 id（update / ingest），或输出引用对象"
            ' {"step": 序号, "field": "course_id"}（指向本计划内建课步骤的输出）'
        ),
    )
    name: str | None = Field(default=None, description="新建课程名称（create_course 必填）")
    learning_context: str | None = Field(
        default=None,
        description="新建课程学习场景（create_course 必填：SCHOOL / CAREER / INTEREST）",
    )
    education_stage: str | None = Field(
        default=None,
        description=("学业教育阶段（SCHOOL 场景必填：如 HIGH_SCHOOL / UNDERGRADUATE / GRADUATE）"),
    )
    depth: str | None = Field(
        default=None,
        description="学习深度（CAREER / INTEREST 场景必填，如 BEGINNER / INTERMEDIATE / ADVANCED）",
    )
    description: str | None = Field(default=None, description="新建课程说明（create_course 可选）")
    url: str | None = Field(default=None, description="导入网页地址（ingest_library_item 必填）")
    depends_on: list[int] | None = Field(
        default=None,
        description="依赖的计划项序号（0 起，必须更早）；依赖项未成功则本项跳过",
    )


class BatchPlanToolArgs(BaseModel):
    """计划工具参数（只暴露计划项：计划版本 / 档位 / 触发指令原文由后端注入）。"""

    model_config = ConfigDict(extra="forbid")

    items: list[BatchPlanItemArgs] = Field(description="本批要整理的对象集合（逐项给出动作与参数）")


@tool(args_schema=BatchPlanToolArgs)
async def plan_batch_operations(**kwargs: Any) -> str:
    """当用户想批量整理资料条目或执行多步任务时使用：把本批目标一次提交为整理计划。

    适用场景：一次整理两条及以上的条目（批量归到某课程、批量改标题、批量归档），
    或多步任务（如「建一个新课程并把这个网页导进去」）。逐项给出 action 与参数：
    update_library_item / archive_library_item 用 item_id（先用 search_library 查找
    消歧取得，课程 id 先用 search_courses 取得）；create_course 给 name 与
    learning_context；ingest_library_item 给 url。后一步参数可引用前一步的输出：
    参数值写成 {"step": 步骤序号, "field": "输出字段"}（如建课步骤输出 course_id）。

    调用后是否需要用户确认由系统按当前授权档位决定：需要时生成一张计划卡（整卡
    一次确认即授权本批次，逐项列出目标与参数），否则直接开始执行并给批次回执。
    计划执行中会有逐项结果；某一步失败不影响其余独立步骤；导入网页的步骤会等待
    后台抓取完成后自动继续。请如实转述返回结果（已出计划卡 / 已开始执行 / 已
    跳过重复目标 / 缺少哪些信息），不要声称任务已经全部完成——执行结果以逐项
    结果与操作历史为准。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"}, ensure_ascii=False)
    payload = await submit_batch_plan(runtime, {"items": _plan_items(kwargs)})
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _plan_items(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """工具宽松参数 → 计划项载荷候选：滤掉未提供（None / 空列表）的字段，
    缺失项与未知键交由载荷判别结构化拒绝（ADR-0024 载荷纪律）。"""
    items: list[dict[str, Any]] = []
    raw_items: object = kwargs.get("items")
    if not isinstance(raw_items, list):
        return items
    for entry in cast("list[object]", raw_items):
        if isinstance(entry, BatchPlanItemArgs):
            raw: dict[str, Any] = entry.model_dump()
        elif isinstance(entry, dict):
            raw = cast("dict[str, Any]", entry)
        else:
            continue
        items.append(
            {key: value for key, value in raw.items() if value is not None and value != []}
        )
    return items
