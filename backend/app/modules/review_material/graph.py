from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import NotRequired

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from typing_extensions import TypedDict

from app.modules.review_material.schemas import ReviewMaterialContent

REVIEW_DECISION_ADJUST = "ADJUST"


class ReviewMaterialState(TypedDict):
    record_id: str
    source_version: int
    review_material: NotRequired[dict[str, object]]
    decision: NotRequired[str]


@dataclass(frozen=True)
class ReviewMaterialRuntime:
    generate: Callable[[], Awaitable[ReviewMaterialContent]]


async def _generate(
    _state: ReviewMaterialState,
    runtime: Runtime[ReviewMaterialRuntime],
) -> dict[str, object]:
    content = await runtime.context.generate()
    return {"review_material": content.model_dump()}


def _review(state: ReviewMaterialState) -> dict[str, object]:
    content = state.get("review_material")
    if content is None:
        raise ValueError("ReviewMaterial Graph 缺少生成结果")
    return {"decision": interrupt({"review_material": content})}


def _route_after_review(state: ReviewMaterialState) -> str:
    return "generate" if state.get("decision") == REVIEW_DECISION_ADJUST else END


def build_review_material_graph(
    checkpointer: BaseCheckpointSaver[str],
) -> CompiledStateGraph[
    ReviewMaterialState,
    ReviewMaterialRuntime,
    ReviewMaterialState,
    ReviewMaterialState,
]:
    builder = StateGraph(ReviewMaterialState, context_schema=ReviewMaterialRuntime)
    builder.add_node("generate", _generate)  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    builder.add_node("review", _review)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "generate")  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge("generate", "review")  # pyright: ignore[reportUnknownMemberType]
    builder.add_conditional_edges(  # pyright: ignore[reportUnknownMemberType]
        "review",
        _route_after_review,
        ["generate", END],  # pyright: ignore[reportArgumentType]
    )
    return builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer,
        name="review-material",
    )
