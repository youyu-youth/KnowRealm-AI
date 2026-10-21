"""轮次事件 → 过程展示投影（历史 REST 与 SSE 流内载荷共用同一规则）。

ChatResponseProcess 保留历史只读；新轮次不再写第二套执行状态机，过程视图
由 ChatTurn 事件投影（规格实施决策 1）。
"""

import json
from collections.abc import Sequence
from typing import Any, cast

from app.modules.agent.schemas import (
    ChatProcessCommentary,
    ChatProcessDelegation,
    ChatProcessTool,
    ChatResponseProcessOut,
    ChatTurnRevisionOut,
)
from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent
from app.modules.agent.turns.schemas import (
    ChatTurnEventType,
    ChatTurnStatus,
    process_status_for_turn,
)

# 仅检索类工具展示命中数（先例：message_service 流式路径的 hits 集合）。
TOOL_HITS_TOOLS = frozenset({"search_library", "search_transcript", "search_courses", "web_search"})

# 轮次停下的状态：未回结果的工具在这些状态下投影为已中断（在途不算中断）。
_STOPPED_TURN_STATUSES = frozenset(
    {
        ChatTurnStatus.INTERRUPTED,
        ChatTurnStatus.FAILED,
        ChatTurnStatus.CANCELLED,
    }
)


def event_payload(row: ChatTurnEvent) -> dict[str, Any]:
    try:
        value: object = json.loads(row.payload_json)
    except ValueError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def project_entries(
    events: Sequence[ChatTurnEvent],
) -> list[ChatProcessCommentary | ChatProcessTool | ChatProcessDelegation]:
    """按 seq 顺序把持久事件投影为过程条目（评注 + 工具卡）。"""
    entries: list[ChatProcessCommentary | ChatProcessTool | ChatProcessDelegation] = []
    delegations: dict[str, ChatProcessDelegation] = {}
    commentary_by_id: dict[str, ChatProcessCommentary] = {}
    tools_by_id: dict[str, ChatProcessTool] = {}
    for row in events:
        payload = event_payload(row)
        event_type = ChatTurnEventType(row.type)
        if event_type == ChatTurnEventType.COMMENTARY and "execution_id" in payload:
            execution_id = str(payload["execution_id"])
            new = ChatProcessDelegation.model_validate({"id": execution_id, **payload})
            previous = delegations.get(execution_id)
            if previous is None:
                entries.append(new)
                delegations[execution_id] = new
            else:
                previous.status, previous.execution_attempt = new.status, new.execution_attempt
                previous.error_code = new.error_code
        elif event_type == ChatTurnEventType.COMMENTARY:
            segment_id = row.segment_id or ""
            text = str(payload.get("text") or "")
            if not text and segment_id not in commentary_by_id:
                continue
            entry = commentary_by_id.get(segment_id)
            if entry is None:
                entry = ChatProcessCommentary(id=segment_id, text=text)
                commentary_by_id[segment_id] = entry
                entries.append(entry)
            else:
                entry.text = text
        elif event_type == ChatTurnEventType.TOOL_CALL:
            entry = ChatProcessTool(
                id=str(payload.get("tool_call_id") or row.tool_call_id or ""),
                tool=str(payload.get("tool") or ""),
                query=str(payload.get("query") or ""),
                status="RUNNING",
            )
            tools_by_id[entry.id] = entry
            entries.append(entry)
        elif event_type == ChatTurnEventType.TOOL_RESULT:
            entry = tools_by_id.get(str(payload.get("tool_call_id") or ""))
            if entry is None:
                continue
            entry.status = (
                "FAILED"
                if not payload.get("ok", True)
                else "AWAITING_CONFIRMATION"
                if payload.get("awaiting_confirmation")
                else "SUCCEEDED"
            )
            if entry.tool in TOOL_HITS_TOOLS:
                hits = payload.get("hits")
                entry.hits = hits if isinstance(hits, int) else 0
    return entries


def build_output_text(events: Sequence[ChatTurnEvent]) -> str:
    """已提交正文投影：done 事件为权威最终快照，否则非评注 segment 按序拼接。

    revision 事件（票 02）声明被替换的未完成 segment：模型节点重放的新正文
    替换它而非拼接两份半段；被替换片段保留在事件流中可查看，不进当前正文。
    """
    segments: dict[str, list[str]] = {}
    commentary_ids: set[str] = set()
    replaced_ids: set[str] = set()
    for row in events:
        event_type = ChatTurnEventType(row.type)
        if event_type == ChatTurnEventType.TOKEN:
            segments.setdefault(row.segment_id or "", []).append(
                str(event_payload(row).get("text") or "")
            )
        elif event_type == ChatTurnEventType.COMMENTARY:
            commentary_ids.add(row.segment_id or "")
        elif event_type == ChatTurnEventType.REVISION:
            replaces = event_payload(row).get("replaces_segment")
            if isinstance(replaces, str) and replaces:
                replaced_ids.add(replaces)
        elif event_type == ChatTurnEventType.DONE:
            return str(event_payload(row).get("content") or "")
    return "".join(
        "".join(parts)
        for segment_id, parts in segments.items()
        if segment_id not in commentary_ids and segment_id not in replaced_ids
    )


def project_revisions(
    events: Sequence[ChatTurnEvent], turn: ChatTurn | None = None
) -> list[ChatTurnRevisionOut]:
    """保留每次替换的旧片段，并关联同版本首个模型片段（可跨刷新查看）。"""
    if turn is not None and turn.snapshot_json is not None:
        saved = json.loads(turn.snapshot_json)["turn"]
        return [ChatTurnRevisionOut.model_validate(item) for item in saved["revisions"]]
    segments: dict[str, list[str]] = {}
    segment_revisions: dict[str, int] = {}
    replacements: list[tuple[str, int]] = []
    for row in events:
        if row.type == ChatTurnEventType.TOKEN.value and row.segment_id:
            segments.setdefault(row.segment_id, []).append(
                str(event_payload(row).get("text") or "")
            )
            segment_revisions[row.segment_id] = row.output_revision
        elif row.type == ChatTurnEventType.REVISION.value:
            replaces = event_payload(row).get("replaces_segment")
            if isinstance(replaces, str) and replaces:
                replacements.append((replaces, row.output_revision))
    return [
        ChatTurnRevisionOut(
            replaces_segment=segment_id,
            previous_revision=segment_revisions[segment_id],
            output_revision=revision,
            previous_text="".join(segments[segment_id]),
            regenerated_text=next(
                (
                    "".join(parts)
                    for new_id, parts in segments.items()
                    if segment_revisions[new_id] == revision
                ),
                "",
            ),
        )
        for segment_id, revision in replacements
        if segment_id in segments
    ]


def process_out_for(
    turn: ChatTurn, events: Sequence[ChatTurnEvent], *, history_saved: bool = True
) -> ChatResponseProcessOut:
    """把轮次投影为历史过程视图（ChatResponseProcessOut 形状，id=turn_id）。"""
    if turn.snapshot_json is not None:
        return ChatResponseProcessOut.model_validate(
            json.loads(turn.snapshot_json)["turn"]["process"]
        )
    status = ChatTurnStatus(turn.status)
    entries = project_entries(events)
    # 只有轮次确实停下（中断/失败/取消）时，未回结果的工具才显示为已中断；仍在
    # 执行（QUEUED/RUNNING/WAITING_*）的轮次保留 RUNNING——工具在途不是中断。
    if status in _STOPPED_TURN_STATUSES:
        for entry in entries:
            if isinstance(entry, ChatProcessTool) and entry.status == "RUNNING":
                entry.status = "INTERRUPTED"
    started = turn.started_at or turn.created_at
    updated = turn.updated_at
    return ChatResponseProcessOut(
        id=turn.id,
        session_id=turn.session_id,
        user_message_id=turn.user_message_id,
        assistant_message_id=turn.final_message_id,
        status=cast("Any", process_status_for_turn(status)),
        started_at=started,
        updated_at=updated,
        ended_at=turn.finished_at,
        elapsed_ms=max(0, round((updated - started).total_seconds() * 1000)),
        entries=entries,
        history_saved=history_saved,
    )
