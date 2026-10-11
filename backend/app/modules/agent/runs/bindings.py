"""Run 计划载荷与输出引用绑定；与受控动作执行分开维护。"""

import json
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.runs.schemas import BatchPlanOut, OperationStatus, params_output_refs
from app.shared.errors import CodedHTTPException


async def resolve_step_refs(
    session: AsyncSession, plan: BatchPlanOut, params: dict[str, Any]
) -> dict[str, Any] | None:
    """输出引用解析（工单 06 结果绑定注入）：来源步骤的 result 按点路径取值。

    返回 None＝不可解析（来源步骤缺失 / 未成功 / 路径无值 / 值非非空字符串），
    调用方按依赖失败跳过——防御路径，正常由「引用即依赖」的前置依赖判定拦截。
    """
    resolved = dict(params)
    entries = {item.index: item for item in plan.items}
    for name, ref in params_output_refs(params).items():
        entry = entries.get(ref.step)
        if entry is None:
            return None
        source = await session.get(AgentOperation, entry.operation_id)
        if (
            source is None
            or source.status != OperationStatus.SUCCEEDED.value
            or source.result_json is None
        ):
            return None
        try:
            parsed: object = json.loads(source.result_json)
        except ValueError:
            return None
        node: object = parsed
        for part in ref.field.split("."):
            if not isinstance(node, dict):
                return None
            node = cast("dict[str, Any]", node).get(part)
        if not isinstance(node, str) or not node:
            return None
        resolved[name] = node
    return resolved


def operation_params(operation: AgentOperation) -> dict[str, Any]:
    """操作载荷 JSON（计划项逐项参数）：坏值转稳定错误码（单项失败不炸推进）。"""
    try:
        value: object = json.loads(operation.payload_json)
    except ValueError as exc:
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="操作载荷不符合该动作的结构要求",
        ) from exc
    if not isinstance(value, dict):
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="操作载荷不符合该动作的结构要求",
        )
    return cast(dict[str, Any], value)
