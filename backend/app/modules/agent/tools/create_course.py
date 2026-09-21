"""创建课程薄工具（通用 Agent 第一阶段工单 02）：操作注册表首个动作的工具壳。

工具语义恒为「创建课程提案」，是否需要用户确认由后端决定（spec 用户故事 19）：
调用成功 = 创建 PENDING 提案，用户在确认卡确认后课程才真实创建。参数 schema
由注册项 payload schema（operations.course_create.CourseCreatePayload）经
registry.lenient_tool_args_schema 派生（spec 决策 3：参数 schema 直接来自注册
项）——同一组字段与类型、全部可选默认 None；必填性与条件校验（学业场景须选
阶段、职业/兴趣须选深度）由注册项 schema 在提案创建时执法（spec 决策 9：缺
必填 → 创建被拒 → 结构化缺失项返回 → 模型转述追问），langchain schema 层
不做硬拦截。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.course_create import (
    CREATE_COURSE_ACTION,
    CourseCreatePayload,
)
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation_proposal,
)
from app.modules.agent.runtime import current_agent_runtime

# 工具名（langchain @tool 注册名 = 函数名）。
CREATE_COURSE_TOOL_NAME = "create_course"


@tool(args_schema=lenient_tool_args_schema(CourseCreatePayload))
async def create_course(**kwargs: Any) -> str:
    """当用户想创建新课程时使用：收集课程信息并创建一条待用户确认的课程提案。

    必填信息：课程名称（name）、学习场景（learning_context，取值 SCHOOL 校园 /
    CAREER 职业 / INTEREST 兴趣）。学业场景必须提供教育阶段（education_stage），
    职业或兴趣场景必须提供学习深度（depth）。课程类型（course_type）与说明
    （description）可选。用户已提供的信息不要重复追问，只追问缺失的必填项；
    信息齐全前不要调用本工具。

    调用成功只是创建了待确认提案：用户在确认卡上确认后课程才会真正创建，
    之后告知用户已生成创建提案、等待其确认。本工具只创建空课程，不包含学习
    记录或 AI 总结等内容；用户要求范围外的能力时如实说明暂不支持，不要承诺。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation_proposal(
        runtime,
        CREATE_COURSE_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
