from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import NotRequired

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from typing_extensions import TypedDict

from app.schemas.summary import SummaryContent


class SummaryState(TypedDict):
    record_id: str
    source_version: int
    summary: NotRequired[dict[str, object]]


@dataclass(frozen=True)
class SummaryRuntime:
    generate: Callable[[], Awaitable[SummaryContent]]


async def _generate(
    _state: SummaryState,
    runtime: Runtime[SummaryRuntime],
) -> dict[str, object]:
    summary = await runtime.context.generate()
    return {"summary": summary.model_dump()}


def _review(state: SummaryState) -> dict[str, object]:
    summary = state.get("summary")
    if summary is None:
        raise ValueError("Summary Graph 缺少生成结果")
    interrupt({"summary": summary})
    return {}


def build_summary_graph(
    checkpointer: BaseCheckpointSaver[str],
) -> CompiledStateGraph[SummaryState, SummaryRuntime, SummaryState, SummaryState]:
    builder = StateGraph(SummaryState, context_schema=SummaryRuntime)
    builder.add_node("generate", _generate)  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    builder.add_node("review", _review)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "generate")
    builder.add_edge("generate", "review")
    builder.add_edge("review", END)
    return builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer,
        name="summary",
    )
