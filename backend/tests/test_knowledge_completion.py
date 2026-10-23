"""双助手修复：真实迁移库、工具、Graph 与 Worker，仅模型边界使用替身。"""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from test_chat_turns import ToolCallReply, create_session, submit, turns_app, wait_terminal
from test_library_retrieval import (
    ITEM_WEB,
    ITEM_WEB_ARCHIVED,
    _insert_item_direct_segments,  # pyright: ignore[reportPrivateUsage]
    retrieval_app,
    seed_scope_corpus,
)
from test_parallel_delegations import delegates, route_model

from app.modules.agent.budget.models import BudgetOutput
from app.modules.agent.budget.policy import calls_remaining, output_remaining
from app.modules.agent.budget.service import restore_runtime
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatScope
from app.modules.agent.tools.search_library import search_library
from app.modules.library.retrieval import LibraryRetrievalService, RetrievalScope


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_batch_returns_four_definitions_and_keeps_literal_scope(tmp_path: Path) -> None:
    topics = ["原子性", "一致性", "隔离性", "持久性"]
    definitions = [f"{topic}是指第{index}个事务保证。" for index, topic in enumerate(topics)]
    async with retrieval_app(tmp_path) as (app, _):
        await seed_scope_corpus(app)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("DELETE FROM document_segments WHERE library_item_id=:id"), {"id": ITEM_WEB}
            )
        await _insert_item_direct_segments(
            app,
            ITEM_WEB,
            [
                part
                for topic, definition in zip(topics, definitions, strict=True)
                for part in (f"- **{topic}：**", definition)
            ],
        )
        runtime = AgentRuntimeContext(
            app.state.session_factory,
            "test",
            scope=ChatScope.LIBRARY_ITEM,
            library_item_id=ITEM_WEB,
        )
        token = bind_agent_runtime_context(runtime)
        try:
            payload = await search_library.ainvoke({"query": topics})
            result = json.loads(payload)
            quotes = [hit["quote"] for hit in result["evidence_hits"]]
            assert all(definition in quotes for definition in definitions), result
            assert len(payload) <= 4000
            assert len(quotes) <= 8 and len(set(quotes)) == len(quotes)
            assert runtime.budget.calls_used == 1
            assert all(hit["library_item_id"] == ITEM_WEB for hit in result["evidence_hits"])
            with pytest.raises(ValidationError):
                await search_library.ainvoke({"query": topics + ["第五项"]})
            async with app.state.session_factory() as session:
                scope = RetrievalScope(ChatScope.LIBRARY_ITEM, library_item_id=ITEM_WEB)
                strict = await LibraryRetrievalService.search(session, scope, "原子性 隔离性 定义")
                assert not strict.evidence_hits
                literal = await LibraryRetrievalService.search(
                    session, scope, "原子性", short_query=True
                )
                assert definitions[0] in [hit.quote for hit in literal.evidence_hits]
                archived = await LibraryRetrievalService.search(
                    session,
                    RetrievalScope(ChatScope.LIBRARY_ITEM, library_item_id=ITEM_WEB_ARCHIVED),
                    "向量",
                    short_query=True,
                )
                assert not archived.evidence_hits
            runtime.budget.chars_fed = 11990
            runtime.budget.root_chars_fed = 35990
            exhausted = json.loads(await search_library.ainvoke({"query": "原子性"}))
            assert exhausted["truncated"] and not exhausted["evidence_hits"]
            assert runtime.budget.chars_fed == 11990
            assert runtime.budget.root_chars_fed == 35990
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("summary", "gaps", "expected"),
    [
        ("已按证据完整回答", [], "COMPLETED"),
        ("已有部分结论", ["定义段未检索到"], "PARTIAL"),
        ("", ["未取得有效证据"], "FAILED"),
        ("报告格式无效", [" "], "FAILED"),
    ],
)
async def test_structured_report_status_without_extra_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, summary: str, gaps: list[str], expected: str
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检查证据"}),
            ToolCallReply(
                "KnowledgeReport",
                {
                    "summary": summary,
                    "gaps": gaps,
                    "citation_lines": ["[1] 只有来源，没有报告正文（来源：测试）"],
                },
                "report",
            ),
            ["汇总已有结果"],
        ],
    ) as (app, client, captured):
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "委派检查", request_id="report-status")).json()["id"]
        assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
        assert len(captured) == 3
        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT status, result_json FROM agent_delegations WHERE turn_id=:id"),
                    {"id": tid},
                )
            ).one()
            assert row.status == expected
            report = json.loads(row.result_json)
            assert bool(report["gaps"]) == (expected != "COMPLETED")
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM chat_turn_budget_calls WHERE turn_id=:id"),
                    {"id": tid},
                )
                == 1
            )


@pytest.mark.anyio
async def test_structured_citation_lines_keep_notes_and_reject_forged_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_shared_refs import COURSE_ML, REC_ML_PAPER, seed_full_corpus

    quote = "梯度下降通过反向传播迭代更新参数。"
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "依据论文解释梯度下降并引用"}),
            ToolCallReply(
                "KnowledgeReport",
                {
                    "summary": "结论[1]。\n\n说明：本报告仅解释所问内容。",
                    "gaps": [],
                    "citation_lines": [
                        f"[1] {quote}（来源：论文精读）",
                        "[2] zzzzzzzzzz（来源：论文精读）",
                    ],
                },
                "report",
            ),
            ["汇总已有证据"],
        ],
    ) as (app, client, captured):
        await seed_full_corpus(app.state.session_factory)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_ML)
        tid = (await submit(client, sid, "委派并给来源", request_id="report-citations")).json()[
            "id"
        ]
        assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
        assert len(captured) == 3
        async with app.state.session_factory() as session:
            raw = await session.scalar(
                text("SELECT result_json FROM agent_delegations WHERE turn_id=:id"), {"id": tid}
            )
            result = json.loads(raw)
            assert result["status"] == "COMPLETED"
            assert "说明：" in result["summary"]
            assert len(result["citations"]) == 1
            assert result["citations"][0]["quote"] == quote
            assert result["citations"][0]["record_id"] == REC_ML_PAPER


@pytest.mark.anyio
async def test_character_totals_restore_per_execution_and_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    routes = {
        "root:characters": [delegates("characters"), ["汇总"]],
        "child:characters:A": [(ToolCallReply("search_library", {"query": "A"}),), release, ["A"]],
        "child:characters:B": [(ToolCallReply("search_library", {"query": "B"}),), release, ["B"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:characters", request_id="character-owners")).json()[
            "id"
        ]
        try:
            for _ in range(150):
                if len(captured) == 5:
                    break
                await asyncio.sleep(0.05)
            assert len(captured) == 5
            async with app.state.session_factory() as session, session.begin():
                calls = (
                    await session.execute(
                        text(
                            "SELECT id, execution_id FROM chat_turn_budget_calls "
                            "WHERE turn_id=:id ORDER BY execution_id"
                        ),
                        {"id": tid},
                    )
                ).all()
                child_calls = [row for row in calls if row.execution_id is not None]
                assert len(child_calls) == 2
                await session.execute(
                    text(
                        "DELETE FROM chat_turn_budget_outputs WHERE call_id IN "
                        "(SELECT id FROM chat_turn_budget_calls WHERE turn_id=:id)"
                    ),
                    {"id": tid},
                )
                session.add(BudgetOutput(id="full-A", call_id=child_calls[0].id, chars_fed=12000))
            first = AgentRuntimeContext(
                app.state.session_factory,
                sid,
                turn_id=tid,
                execution_id=child_calls[0].execution_id,
            )
            second = AgentRuntimeContext(
                app.state.session_factory,
                sid,
                turn_id=tid,
                execution_id=child_calls[1].execution_id,
            )
            await restore_runtime(first)
            await restore_runtime(second)
            assert first.budget.chars_fed == first.budget.root_chars_fed == 12000
            assert output_remaining(first.budget) == 0
            assert second.budget.chars_fed == 0 and second.budget.root_chars_fed == 12000
            assert output_remaining(second.budget) == 12000
            assert second.budget.calls_used == 1 and second.budget.root_calls_used == 4
            async with app.state.session_factory() as session, session.begin():
                session.add(BudgetOutput(id="full-root", call_id=calls[0].id, chars_fed=24000))
            await restore_runtime(second)
            assert second.budget.root_chars_fed == 36000
            assert output_remaining(second.budget) == 0
            second.budget.root_calls_used = 18
            assert calls_remaining(second.budget) == 0
        finally:
            release.set()
        await wait_terminal(client, tid)
