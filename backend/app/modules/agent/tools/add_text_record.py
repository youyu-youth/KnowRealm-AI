"""向课程添加文本记录薄工具（通用 Agent 第一阶段工单 03）：操作注册表第二动作。

工具语义恒为「完成向课程添加文本记录」（spec 用户故事 19）：调用成功 = 创建
PENDING 提案，用户在确认卡确认后记录才真实保存。参数 schema 由注册项 payload
schema（agent.schemas.TextRecordAddPayload）经 registry.lenient_tool_args_schema
派生——同一组字段与类型、全部可选默认 None；必填与正文上限由注册项 schema 在
提案创建时执法（空/缺失 → 结构化缺失项、超 1 MiB → detail），模型转述追问。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.operations.text_record_add import ADD_TEXT_RECORD_ACTION
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import TextRecordAddPayload

# 工具名（langchain @tool 注册名 = 函数名）。
ADD_TEXT_RECORD_TOOL_NAME = "add_text_record_to_course"


@tool(args_schema=lenient_tool_args_schema(TextRecordAddPayload))
async def add_text_record_to_course(**kwargs: Any) -> str:
    """当用户想把一段文本保存为某课程的学习记录时使用：创建一条待用户确认的添加提案。

    必填：course_id（目标课程 id）、content（要保存的文本正文，上限 1 MiB）。
    不确定目标课程时先用 search_courses 按名称查找：唯一匹配直接使用；多个候选
    时列出候选（名称、状态、场景、更新时间）让用户选择；找不到时明确告知，
    不要擅自新建课程。记录标题自动取正文首行前 100 字，不要单独追问标题。

    保存后将自动尝试生成 AI 总结——这是当前唯一的保存形态；用户要求「只保存、
    不生成总结」时如实告知暂不支持，不要承诺。调用成功只是创建了待确认提案：
    用户在确认卡上确认后记录才会真正保存。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        ADD_TEXT_RECORD_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
