import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, ClassVar, cast
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    UsageMetadata,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from loguru import logger
from sqlalchemy import text, update

from app.main import create_app
from app.modules.agent.citations import (
    LibraryRecordMaterial,
    parse_citation_reply,
    parse_library_citation_reply,
)
from app.modules.agent.context import (
    CHAT_BATCH_PLAN_GUIDANCE,
    CHAT_CONTEXT_CHAR_BUDGET,
    CHAT_ENUMERATION_GUIDANCE,
    CHAT_GOAL_GUIDANCE,
    CHAT_LANGUAGE_INSTRUCTION,
    CHAT_PLAN_GUIDANCE,
    CHAT_RUN_BINDING_GUIDANCE,
    CHAT_SHARED_REF_GUIDANCE,
    CHAT_UNDO_GUIDANCE,
    ChatContextTooLargeError,
    ContextRow,
    LibraryContext,
    LibraryRecordRow,
    RecordContext,
    build_context_messages,
)
from app.modules.agent.graph import build_chat_agent
from app.modules.agent.message_service import (
    _cited_excerpts,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.models import ChatMessage
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatRole, ChatScope
from app.modules.agent.tools.search_library import search_library
from app.modules.course_brain.service import normalize_concept_name
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.library.retrieval import LibraryRetrievalService
from app.modules.search.integrations.tavily import TavilySearchClient
from app.modules.search.segment_service import (
    ENTITY_CONCEPT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.search.tokenizer import tokenize
from app.modules.settings.config import save_llm_provider, save_web_search_provider
from app.modules.settings.model_budget import ModelBudgetConfig
from app.modules.summary.models import AiSummary
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-15T00:00:00Z"

STUB_REPLY = ["回答", "完成", "了"]


@dataclass(frozen=True)
class ToolCallReply:
    """假模型的一次工具调用响应：单个完整 tool_call chunk（args 一次给全）。

    args_fragments 非 None 时按给定片段流式发出 args（模拟真实供应商分片，
    首片带 name/id），用于验证未闭合 JSON 不会被提前上报。
    """

    tool: str
    args: dict[str, Any]
    call_id: str = "call-1"
    args_fragments: tuple[str, ...] | None = None
    commentary: str = ""
    parallel_calls: tuple["ToolCallReply", ...] = ()


@dataclass(frozen=True)
class GatedReply:
    """受控回复：先吐 prefix 分片，随后挂起等待 release（取消 / 并发测试用）。

    挂起点即「生成在途」的确定性窗口：取消观察器 / 冲突提交在此期间行动，
    release 置位后继续吐 rest（取消路径下生成器已被取消，置位无副作用）。
    """

    prefix: tuple[str, ...]
    release: asyncio.Event
    rest: tuple[str, ...] = ("收尾",)


StubReply = list[str] | ToolCallReply | GatedReply | None


def row(row_id: str, role: ChatRole, content: str) -> ContextRow:
    return ContextRow(id=row_id, role=role, content=content)


def chat_rows(count: int, *, prefix: str = "") -> list[ContextRow]:
    """构造 count 个完整 user→assistant 往返轮。"""
    return [
        item
        for index in range(1, count + 1)
        for item in (
            row(f"{prefix}u{index}", ChatRole.USER, f"{prefix}问题{index}"),
            row(f"{prefix}a{index}", ChatRole.ASSISTANT, f"{prefix}回答{index}"),
        )
    ]


class TestBuildContextMessages:
    def test_oversize_assets_are_not_silently_truncated_or_sent_over_budget(self) -> None:
        with pytest.raises(ChatContextTooLargeError):
            build_context_messages(
                [row("current", ChatRole.USER, "追问")],
                record=RecordContext(transcript="长" * 30001, knowledge_points="知" * 60000),
            )

    def test_mounted_transcript_stays_when_oldest_turn_is_trimmed(self) -> None:
        rows = [*chat_rows(2), row("current", ChatRole.USER, "追问")]
        mounted = RecordContext(transcript="原文🧠" * 7500)
        messages = build_context_messages(rows, record=mounted)
        assert mounted.transcript in str(messages[0].content)
        # 上限恰好容纳一轮和当前提问，下一字符才触发裁剪。
        required = len(str(messages[0].content)) + 8
        trimmed = build_context_messages(rows, record=mounted, budget=required)
        assert [message.content for message in trimmed[1:]] == ["问题2", "回答2", "追问"]
        assert trimmed[0].content == messages[0].content
        under = build_context_messages(rows, record=mounted, budget=required - 1)
        assert [message.content for message in under[1:]] == ["追问"]

    def test_long_transcript_uses_assets_and_only_last_three_completed_turns_excerpts(self) -> None:
        rows = [
            item
            for index in range(1, 5)
            for item in (
                row(f"u{index}", ChatRole.USER, f"问题{index}"),
                ContextRow(
                    id=f"a{index}",
                    role=ChatRole.ASSISTANT,
                    content=f"回答{index}",
                    cited_excerpts=(f"摘录{index}",),
                ),
            )
        ]
        rows.append(row("pending", ChatRole.USER, "尚未回复"))
        transcript = "长" * 30001 + "摘录1 摘录2 摘录3 摘录4"
        messages = build_context_messages(
            rows,
            record=RecordContext(
                transcript=transcript, summary="已确认摘要", knowledge_points="知识点全文"
            ),
        )
        source = str(messages[0].content)
        assert transcript not in source
        assert "已确认摘要" in source and "知识点全文" in source
        assert "摘录1" not in source
        assert all(f"摘录{index}" in source for index in (2, 3, 4))
        assert messages[-1].content == "尚未回复"

    def test_keeps_system_snapshot_first_with_stable_row_id(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "你是学习助手"),
                row("u1", ChatRole.USER, "问题"),
                row("a1", ChatRole.ASSISTANT, "回答"),
            ]
        )

        assert len(messages) == 3
        assert isinstance(messages[0], SystemMessage)
        # 有效 SYSTEM 消息末尾统一携带对象枚举指引、批量整理指引与语言指令（决策 #59）。
        assert messages[0].content == (
            "你是学习助手\n"
            f"{CHAT_ENUMERATION_GUIDANCE}\n"
            f"{CHAT_BATCH_PLAN_GUIDANCE}\n{CHAT_UNDO_GUIDANCE}\n{CHAT_GOAL_GUIDANCE}\n"
            f"{CHAT_PLAN_GUIDANCE}\n"
            f"{CHAT_SHARED_REF_GUIDANCE}\n"
            f"{CHAT_RUN_BINDING_GUIDANCE}\n"
            f"{CHAT_LANGUAGE_INSTRUCTION}"
        )
        assert messages[0].id == "sys"
        assert isinstance(messages[1], HumanMessage)
        assert isinstance(messages[2], AIMessage)
        assert [message.id for message in messages] == ["sys", "u1", "a1"]

    def test_window_keeps_last_ten_turns_and_drops_oldest(self) -> None:
        messages = build_context_messages([row("sys", ChatRole.SYSTEM, "S"), *chat_rows(11)])

        contents = [message.content for message in messages]
        assert "问题1" not in contents
        assert "回答1" not in contents
        assert "问题2" in contents
        assert "问题11" in contents and "回答11" in contents
        # SYSTEM + 10 轮 × 2 条 = 21 条
        assert len(messages) == 21

    def test_trailing_unanswered_user_counts_as_current_turn(self) -> None:
        # 10 个完成轮全部在窗口内，末尾未回复 user 作为当前提问额外附加、不占窗口。
        messages = build_context_messages(
            [row("sys", ChatRole.SYSTEM, "S"), *chat_rows(10), row("u11", ChatRole.USER, "追问")]
        )

        contents = [message.content for message in messages]
        assert "问题1" in contents
        assert "追问" in contents
        assert len(messages) == 1 + 10 * 2 + 1

    def test_interrupted_turn_excluded_from_completed_turn_count(self) -> None:
        # 中断轮（孤立 user）不计入 10 轮窗口：9 完整轮 + 孤立 user 时最旧完整轮保留。
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                *chat_rows(9),
                row("u10", ChatRole.USER, "中断的问题"),
            ]
        )

        contents = [message.content for message in messages]
        assert "问题1" in contents  # 只有 9 个完整轮 + 当前孤立 user = 10 轮内
        assert "中断的问题" in contents

    def test_budget_drops_oldest_turns_until_within_budget(self) -> None:
        # 每轮 6 字符（"问题N"+"回答N"），SYSTEM 快照含语言指令、枚举与批量指引：
        # budget 取 3 轮轮身 + 快照 + 1，保证恰好容纳 3 轮。
        system_len = len(
            "\n".join(
                [
                    "S",
                    CHAT_ENUMERATION_GUIDANCE,
                    CHAT_BATCH_PLAN_GUIDANCE,
                    CHAT_UNDO_GUIDANCE,
                    CHAT_GOAL_GUIDANCE,
                    CHAT_PLAN_GUIDANCE,
                    CHAT_SHARED_REF_GUIDANCE,
                    CHAT_RUN_BINDING_GUIDANCE,
                    CHAT_LANGUAGE_INSTRUCTION,
                ]
            )
        )
        messages = build_context_messages(
            [row("sys", ChatRole.SYSTEM, "S"), *chat_rows(5)],
            budget=system_len + 3 * 6 + 1,
        )

        contents = [message.content for message in messages]
        assert "问题1" not in contents and "问题2" not in contents
        assert "问题3" in contents and "回答5" in contents

    def test_budget_never_drops_current_question(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                *chat_rows(3),
                row("u4", ChatRole.USER, "这是一个相当长的当前提问" * 20),
            ],
            budget=50,
        )

        contents = [message.content for message in messages]
        assert "这是一个相当长的当前提问" * 20 in contents
        assert "问题3" not in contents

    def test_skips_tool_rows(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                row("u1", ChatRole.USER, "问题"),
                row("t1", ChatRole.TOOL, "工具输出"),
                row("a1", ChatRole.ASSISTANT, "回答"),
            ]
        )

        assert [message.content for message in messages] == [
            "\n".join(
                [
                    "S",
                    CHAT_ENUMERATION_GUIDANCE,
                    CHAT_BATCH_PLAN_GUIDANCE,
                    CHAT_UNDO_GUIDANCE,
                    CHAT_GOAL_GUIDANCE,
                    CHAT_PLAN_GUIDANCE,
                    CHAT_SHARED_REF_GUIDANCE,
                    CHAT_RUN_BINDING_GUIDANCE,
                    CHAT_LANGUAGE_INSTRUCTION,
                ]
            ),
            "问题",
            "回答",
        ]

    def test_default_budget_constant(self) -> None:
        assert CHAT_CONTEXT_CHAR_BUDGET == 60000


class TestParseCitationReply:
    TRANSCRIPT = "MVCC 依赖 undo 日志实现多版本读，写入时保留旧版本。"

    def test_trailing_block_stripped_and_validated(self) -> None:
        parsed = parse_citation_reply(
            "MVCC 依赖 undo 日志[1]。\n\n"
            "[1] MVCC 依赖 undo 日志实现多版本读\n[2] 转写中不存在的摘录",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        assert parsed.content == "MVCC 依赖 undo 日志[1]。"
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "quote": "MVCC 依赖 undo 日志实现多版本读",
            }
        ]

    def test_web_line_becomes_web_entry_without_verbatim_check(self) -> None:
        parsed = parse_citation_reply(
            "MVCC 依赖 undo 日志[1]，最新动态见官方博客[2]。\n"
            "[1] MVCC 依赖 undo 日志实现多版本读\n"
            "[2] Tavily 官方博客 — https://tavily.com/blog。",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        # 混合引用块：URL 行 → web 条目（不逐字校验、容忍尾部句读），转写行照旧校验。
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "quote": "MVCC 依赖 undo 日志实现多版本读",
            },
            {
                "index": 2,
                "source": "web",
                "url": "https://tavily.com/blog",
                "title": "Tavily 官方博客",
            },
        ]
        assert parsed.content == "MVCC 依赖 undo 日志[1]，最新动态见官方博客[2]。"

    def test_web_line_without_title_dropped(self) -> None:
        parsed = parse_citation_reply(
            "回答[1]。\n[1] https://example.com",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        # 仅非空检查：裸 URL 无标题整条丢弃（引用块仍剥离）。
        assert parsed.citations == []
        assert parsed.content == "回答[1]。"

    def test_blockquote_and_list_prefix_lines_recognized(self) -> None:
        parsed = parse_citation_reply(
            "MVCC 依赖 undo 日志[1]。\n"
            "> [1] MVCC 依赖 undo 日志实现多版本读\n"
            "- [2] 写入时保留旧版本",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        assert parsed.content == "MVCC 依赖 undo 日志[1]。"
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "quote": "MVCC 依赖 undo 日志实现多版本读",
            },
            {"index": 2, "source": "record", "record_id": "rec-1", "quote": "写入时保留旧版本"},
        ]

    def test_paraphrased_quote_aligned_to_real_transcript_line(self) -> None:
        transcript = (
            "Docker 是一个用于开发、交付和运行应用程序的开放平台。\n"
            "容器共享宿主机内核，比虚拟机更轻量。"
        )
        parsed = parse_citation_reply(
            "Docker 是容器化平台[1]。\n"
            "[1] Docker是用于开发、交付和运行应用程序的开放平台，使应用与基础架构分离。",
            transcript=transcript,
            record_id="rec-1",
        )
        # 意译摘录不在原文中，但相似度达标：以真实原句替换展示，跳转定位天然命中。
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "quote": "Docker 是一个用于开发、交付和运行应用程序的开放平台。",
            }
        ]

    def test_unrelated_paraphrase_dropped(self) -> None:
        parsed = parse_citation_reply(
            "回答[1]。\n[1] 与材料毫无关系的另一句话",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        assert parsed.citations == []
        # 引用块被识别即剥离，即使全部条目未通过校验。
        assert parsed.content == "回答[1]。"

    def test_index_zero_dropped(self) -> None:
        parsed = parse_citation_reply(
            "[0] MVCC 依赖 undo 日志实现多版本读",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        # index 与 API 侧 ChatCitationOut.ge=1 对齐：[0] 整条丢弃，引用块仍剥离。
        assert parsed.citations == []
        assert parsed.content == ""

    def test_quote_over_80_chars_aligned_to_bounded_window(self) -> None:
        long_quote = "长" * 81
        transcript_line = f"开头{long_quote}结尾"
        parsed = parse_citation_reply(
            f"正文[1]\n[1] {long_quote}",
            transcript=transcript_line,
            record_id="rec-1",
        )
        # 超长摘录不再直接丢弃：对齐到真实原文并以 ≤80 字窗口替换。
        assert len(parsed.citations) == 1
        aligned = parsed.citations[0]["quote"]
        assert isinstance(aligned, str)
        assert len(aligned) <= 80
        assert aligned in transcript_line
        assert parsed.content == "正文[1]"

    def test_without_trailing_block_content_untouched(self) -> None:
        text = "第一步[1] 做事\n第二步 继续做"  # 角标在正文中间、文末不是引用行
        parsed = parse_citation_reply(text, transcript=self.TRANSCRIPT, record_id="rec-1")
        assert parsed.content == text
        assert parsed.citations == []

    def test_block_only_reply_leaves_empty_content(self) -> None:
        parsed = parse_citation_reply(
            "[1] MVCC 依赖 undo 日志实现多版本读",
            transcript=self.TRANSCRIPT,
            record_id="rec-1",
        )
        assert parsed.content == ""
        assert len(parsed.citations) == 1


class TestBuildContextMessagesLibrary:
    def test_library_listing_replaces_system_and_carries_citation_format(self) -> None:
        messages = build_context_messages(
            [row("sys", ChatRole.SYSTEM, "角色快照"), row("u1", ChatRole.USER, "这门课讲了什么")],
            library=LibraryContext(
                scope_label="课程「分布式系统」",
                records=(
                    LibraryRecordRow(
                        title="第 2 讲 一致性哈希", updated_date="2026-09-10", has_transcript=True
                    ),
                    LibraryRecordRow(
                        title="闪念速记", updated_date="2026-09-12", has_transcript=False
                    ),
                ),
            ),
        )
        prompt = str(messages[0].content)
        # 角色快照让位清单指令：标题 + 日期 + 无转写标注 + 检索指引 + 跨记录引用格式。
        assert "角色快照" not in prompt
        assert "课程「分布式系统」" in prompt
        assert "第 2 讲 一致性哈希（2026-09-10）" in prompt
        assert "闪念速记（2026-09-12，暂无转写）" in prompt
        assert "search_library" in prompt
        assert "（来源：来源标题）" in prompt
        assert messages[-1].content == "这门课讲了什么"

    def test_empty_library_states_no_records_honestly(self) -> None:
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "有哪些资料")],
            library=LibraryContext(scope_label="全部资料", records=()),
        )
        prompt = str(messages[0].content)
        assert "共 0 条学习记录" in prompt
        assert "当前资料中未找到" in prompt

    def test_listing_budget_keeps_most_recent_with_note(self) -> None:
        # 记录行按 updated_at 降序传入（加载器语义）：预算内保留最前（最近）的记录。
        rows = tuple(
            LibraryRecordRow(title=f"记录{i}", updated_date="2026-09-01", has_transcript=True)
            for i in range(499, -1, -1)
        )
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "问")],
            library=LibraryContext(scope_label="全部资料", records=rows),
        )
        prompt = str(messages[0].content)
        assert "共 500 条学习记录，仅列最近" in prompt
        assert "记录499" in prompt and "记录0" not in prompt

    def test_library_web_search_guidance_keeps_materials_first(self) -> None:
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "问")],
            library=LibraryContext(scope_label="全部资料", records=()),
            web_search=True,
        )
        assert "仅作为材料外的补充来源" in str(messages[0].content)

    def test_item_content_injected_with_source_headers(self) -> None:
        # LIBRARY_ITEM 档正文注入：段头【来源：标题】+ 优先正文指令 + 引用放宽措辞。
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "这份资料讲了什么")],
            library=LibraryContext(
                scope_label="资料「傅里叶笔记」及其关联学习记录",
                records=(
                    LibraryRecordRow(
                        title="傅里叶笔记", updated_date="2026-09-19", has_transcript=True
                    ),
                ),
                item_content="【来源：傅里叶笔记】\n本讲系统梳理傅里叶级数的展开方法",
            ),
        )
        prompt = str(messages[0].content)
        assert "资料正文（优先依据正文回答" in prompt
        assert "【来源：傅里叶笔记】" in prompt
        assert "本讲系统梳理傅里叶级数的展开方法" in prompt
        assert "优先依据上方资料正文回答" in prompt
        assert "逐字来自资料正文或 evidence_hits" in prompt

    def test_item_content_empty_states_pending_hint(self) -> None:
        # 无可用正文（处理中/失败）：注入未就绪提示，不再让模型回答「未找到」误导。
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "讲了什么")],
            library=LibraryContext(
                scope_label="资料「傅里叶笔记」及其关联学习记录", records=(), item_content=""
            ),
        )
        prompt = str(messages[0].content)
        assert "暂无可用正文" in prompt
        assert "尚未就绪" in prompt
        assert "资料正文（优先依据正文回答" not in prompt

    def test_item_content_none_keeps_listing_only(self) -> None:
        # None（非 LIBRARY_ITEM 档 / 超 30k 降级）：清单 + 检索模式与现状一致。
        messages = build_context_messages(
            [row("u1", ChatRole.USER, "问")],
            library=LibraryContext(scope_label="全部资料", records=()),
        )
        prompt = str(messages[0].content)
        assert "资料正文（优先依据正文回答" not in prompt
        assert "需要资料原文细节时" in prompt


class TestParseLibraryCitationReply:
    RECORDS = [
        LibraryRecordMaterial(
            record_id="rec-1",
            title="第 2 讲 一致性哈希",
            transcript="第二讲聚焦一致性哈希的实践应用。",
        ),
        LibraryRecordMaterial(
            record_id="rec-2",
            title="第 5 讲 分布式共识",
            transcript="第五讲聚焦一致性哈希的理论证明。这里的共识协议是 Raft。",
        ),
    ]

    def test_source_title_locates_record_and_passes_verbatim(self) -> None:
        parsed = parse_library_citation_reply(
            "第 2 讲更强调实践[1]。\n"
            "[1] 第二讲聚焦一致性哈希的实践应用（来源：第 2 讲 一致性哈希）",
            self.RECORDS,
        )
        assert parsed.content == "第 2 讲更强调实践[1]。"
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "record_title": "第 2 讲 一致性哈希",
                "quote": "第二讲聚焦一致性哈希的实践应用",
            }
        ]

    def test_duplicate_titles_verify_each_and_take_first_pass(self) -> None:
        records = [
            LibraryRecordMaterial("rec-a", "同名讲义", "内容甲，不含目标句。"),
            LibraryRecordMaterial("rec-b", "同名讲义", "目标句出现在第二条同名记录里。"),
        ]
        parsed = parse_library_citation_reply(
            "见原文[1]。\n[1] 目标句出现在第二条同名记录里（来源：同名讲义）",
            records,
        )
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-b",
                "record_title": "同名讲义",
                "quote": "目标句出现在第二条同名记录里",
            }
        ]

    def test_unknown_title_dropped_without_scope_wide_fallback(self) -> None:
        parsed = parse_library_citation_reply(
            "回答[1]。\n[1] 第五讲聚焦一致性哈希的理论证明（来源：不存在的标题）",
            self.RECORDS,
        )
        # 标题定位失败不做全范围兜底：摘录真实存在也丢弃（归属不可信）。
        assert parsed.citations == []
        assert parsed.content == "回答[1]。"

    def test_bare_quote_scans_scope_verbatim_and_takes_first_container(self) -> None:
        records = [
            LibraryRecordMaterial("rec-a", "甲", "这句话只在后一条出现。"),
            LibraryRecordMaterial("rec-b", "乙", "裸摘录没有来源标记。"),
        ]
        parsed = parse_library_citation_reply("两种形态[1]。\n[1] 裸摘录没有来源标记", records)
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-b",
                "record_title": "乙",
                "quote": "裸摘录没有来源标记",
            }
        ]

    def test_bare_quote_miss_dropped_without_fuzzy_alignment(self) -> None:
        parsed = parse_library_citation_reply(
            "回答[1]。\n[1] 裸摘录意译版本与任何记录都不逐字相同",
            self.RECORDS,
        )
        assert parsed.citations == []

    def test_paraphrase_aligned_only_within_title_located_candidates(self) -> None:
        transcript = "一致性哈希把节点映射到哈希环上，实现均匀分布。"
        records = [
            LibraryRecordMaterial("rec-a", "甲", "无关内容一句。"),
            LibraryRecordMaterial("rec-b", "哈希讲义", transcript),
        ]
        parsed = parse_library_citation_reply(
            "见下[1]。\n[1] 一致性哈希将节点映射至哈希环，从而实现均匀的分布（来源：哈希讲义）",
            records,
        )
        assert len(parsed.citations) == 1
        entry = parsed.citations[0]
        assert entry["record_id"] == "rec-b"
        assert entry["quote"] == "一致性哈希把节点映射到哈希环上，实现均匀分布。"

    def test_web_line_and_parenthesis_variants(self) -> None:
        parsed = parse_library_citation_reply(
            "本地与网络并存[1][2]。\n"
            "[1] 第二讲聚焦一致性哈希的实践应用（来源：《第 2 讲 一致性哈希》）\n"
            "[2] 共识博客 — https://example.com/raft。",
            self.RECORDS,
        )
        assert parsed.citations == [
            {
                "index": 1,
                "source": "record",
                "record_id": "rec-1",
                "record_title": "第 2 讲 一致性哈希",
                "quote": "第二讲聚焦一致性哈希的实践应用",
            },
            {"index": 2, "source": "web", "url": "https://example.com/raft", "title": "共识博客"},
        ]
        assert parsed.content == "本地与网络并存[1][2]。"

    def test_half_width_parenthesis_source_marker_accepted(self) -> None:
        parsed = parse_library_citation_reply(
            "见[1]。\n[1] 第五讲聚焦一致性哈希的理论证明 (来源: 第 5 讲 分布式共识)",
            self.RECORDS,
        )
        assert len(parsed.citations) == 1
        assert parsed.citations[0]["record_id"] == "rec-2"

    def test_without_trailing_block_content_untouched(self) -> None:
        text = "正文中间的[1]角标不算引用块"
        parsed = parse_library_citation_reply(text, self.RECORDS)
        assert parsed.content == text
        assert parsed.citations == []


class StubChatModel(BaseChatModel):
    """测试缝隙：捕获喂入的消息列表，按队列逐 token 吐出预设回复。

    replies 队列元素为分片列表（None 表示该次调用抛错、ToolCallReply 表示
    该次调用发起工具调用）；captured / replies 用类级共享（ClassVar），
    跨每请求新建的实例累积。
    """

    captured: ClassVar[list[list[AnyMessage]]] = []
    replies: ClassVar[list[StubReply]] = []

    @property
    def _llm_type(self) -> str:
        return "stub-test"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError

    async def _astream(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        type(self).captured.append(list(messages))
        reply = type(self).replies.pop(0)
        if isinstance(reply, GatedReply):
            for part in reply.prefix:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))
            await reply.release.wait()
            for part in reply.rest:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))
            return
        if isinstance(reply, ToolCallReply):
            if reply.commentary:
                yield ChatGenerationChunk(message=AIMessageChunk(content=reply.commentary))
            for tool_index, call in enumerate((reply, *reply.parallel_calls)):
                fragments = call.args_fragments or (json.dumps(call.args, ensure_ascii=False),)
                for index, fragment in enumerate(fragments):
                    first = index == 0
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": call.tool if first else None,
                                    "args": fragment,
                                    "id": call.call_id if first else None,
                                    "index": tool_index,
                                }
                            ],
                            usage_metadata=(
                                UsageMetadata(input_tokens=3, output_tokens=4, total_tokens=7)
                                if tool_index == 0 and index == len(fragments) - 1
                                else None
                            ),
                        )
                    )
            return
        if reply is None:
            raise RuntimeError("stub provider down")
        for index, part in enumerate(reply):
            usage = (
                UsageMetadata(input_tokens=3, output_tokens=4, total_tokens=7)
                if index == len(reply) - 1
                else None
            )
            yield ChatGenerationChunk(message=AIMessageChunk(content=part, usage_metadata=usage))

    def bind(self, **kwargs: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        return self


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def streaming_chat_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replies: Sequence[StubReply] | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, list[list[AnyMessage]]]]:
    captured: list[list[AnyMessage]] = []
    queue: list[StubReply] = list(replies) if replies is not None else [list(STUB_REPLY)]

    class _StubChatOpenAI(StubChatModel):
        pass

    _StubChatOpenAI.captured = captured
    _StubChatOpenAI.replies = queue
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", _StubChatOpenAI)

    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
        model_budget=ModelBudgetConfig(context_window=128000),
    )
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, captured


async def read_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if event_name is not None:
                payload = json.loads("\n".join(data_lines))
                events.append((event_name, cast(dict[str, Any], payload)))
            event_name, data_lines = None, []
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    return events


async def send_message(
    client: httpx.AsyncClient,
    session_id: str,
    content: str,
    *,
    web_search: bool = False,
    page: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """提交轮次并订阅事件到终态（票 01 提交/订阅契约；返回与旧流同词汇的事件列表）。"""
    body: dict[str, Any] = {
        "content": content,
        "web_search": web_search,
        "request_id": request_id or str(uuid4()),
    }
    if page is not None:
        body["page"] = page
    submitted = await client.post(f"/api/chat-sessions/{session_id}/turns", json=body)
    assert submitted.status_code == 202, submitted.text
    turn_id = submitted.json()["id"]
    async with client.stream("GET", f"/api/chat-turns/{turn_id}/events?after_seq=0") as response:
        assert response.status_code == 200
        return await read_sse(response)


async def submit_turn(
    client: httpx.AsyncClient,
    session_id: str,
    content: str,
    *,
    web_search: bool = False,
    page: dict[str, Any] | None = None,
    auth_mode: str | None = None,
) -> str:
    """提交轮次（不订阅事件流）：返回 turn_id（取消 / 冲突类测试的入口）。"""
    body: dict[str, Any] = {
        "content": content,
        "web_search": web_search,
        "request_id": str(uuid4()),
    }
    if page is not None:
        body["page"] = page
    if auth_mode is not None:
        body["auth_mode"] = auth_mode
    submitted = await client.post(f"/api/chat-sessions/{session_id}/turns", json=body)
    assert submitted.status_code == 202, submitted.text
    return cast(str, submitted.json()["id"])


async def wait_turn_terminal(
    client: httpx.AsyncClient, turn_id: str, timeout_seconds: float = 15.0
) -> dict[str, Any]:
    """轮询轮次快照直到终态（返回快照 JSON）。"""
    for _ in range(int(timeout_seconds / 0.1)):
        body = cast(dict[str, Any], (await client.get(f"/api/chat-turns/{turn_id}")).json())
        if body["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            return body
        await asyncio.sleep(0.1)
    pytest.fail(f"轮次未达终态: {turn_id}")


async def wait_turn_progress(client: httpx.AsyncClient, turn_id: str, min_seq: int) -> None:
    """等待轮次推进（last_seq ≥ min_seq 且在途）：取消测试的确定性前置。"""
    for _ in range(150):
        body = cast(dict[str, Any], (await client.get(f"/api/chat-turns/{turn_id}")).json())
        if body["status"] == "RUNNING" and body["last_seq"] >= min_seq:
            return
        if body["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            pytest.fail(f"轮次提前终态: {body['status']}")
        await asyncio.sleep(0.1)
    pytest.fail("轮次未推进")


async def message_rows(data_dir: Path, session_id: str) -> list[tuple[str, str]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return [
            (cast(str, item[0]), cast(str, item[1]))
            for item in await (
                await connection.execute(
                    "SELECT role, content FROM chat_messages"
                    " WHERE session_id = ? ORDER BY created_at, id",
                    (session_id,),
                )
            ).fetchall()
        ]


async def chat_log_rows(data_dir: Path) -> list[Sequence[Any]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return list(
            await (
                await connection.execute(
                    "SELECT graph_name, graph_node, model, prompt_version,"
                    " token_usage_json, error_code FROM llm_call_logs"
                    " WHERE graph_name = 'chat'"
                )
            ).fetchall()
        )


async def create_session(client: httpx.AsyncClient) -> str:
    created = await client.post("/api/chat-sessions", json={})
    assert created.status_code == 201
    return cast(str, created.json()["id"])


async def wait_for_transcript_ready(client: httpx.AsyncClient, record_id: str) -> None:
    for _ in range(250):
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/transcript")).json(),
        )
        if payload.get("status") == "READY":
            return
        await asyncio.sleep(0.02)
    pytest.fail("转写未落稿")


@pytest.mark.anyio
async def test_mounted_stream_reads_current_transcript_without_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        _app,
        client,
        captured,
    ):
        await client.put(
            "/api/profile", json={"primary_role": "DEVELOPER", "about_me": "角色专用文本"}
        )
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "原始公式 x+y"}
        )
        assert capture.status_code == 201
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert (await send_message(client, session_id, "后面那个公式？"))[-1][0] == "done"
        prompt = str(captured[0][0].content)
        assert "原始公式 x+y" in prompt
        assert "角色专用文本" not in prompt and "程序员" not in prompt

        edited = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "修订公式 x-y", "expected_source_version": 1},
        )
        assert edited.status_code == 200
        assert (await send_message(client, session_id, "现在的公式？"))[-1][0] == "done"
        assert "修订公式 x-y" in str(captured[1][0].content)
        assert "原始公式 x+y" not in str(captured[1][0].content)
        assert "后面那个公式？" in [message.content for message in captured[1]]


@pytest.mark.anyio
async def test_knowledge_point_entry_snapshots_focus_context_and_keeps_multiturn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        _app,
        client,
        captured,
    ):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "调度器原文"}
        )
        record_id = capture.json()["record_id"]
        point = await client.post(
            f"/api/records/{record_id}/knowledge-points",
            json={
                "name": "进程调度",
                "detail": "调度器从就绪队列选择下一个运行的进程。",
                "tags": ["操作系统"],
                "importance": 5,
            },
        )
        assert point.status_code == 201

        created = await client.post(
            "/api/chat-sessions",
            json={"record_id": record_id, "knowledge_point_id": point.json()["id"]},
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        updated = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{point.json()['id']}",
            json={
                "name": "已修改名称",
                "detail": "已修改详情",
                "tags": [],
                "importance": 1,
            },
        )
        assert updated.status_code == 200

        assert (await send_message(client, session_id, "给我讲讲它"))[-1][0] == "done"
        assert (await send_message(client, session_id, "再举个例子"))[-1][0] == "done"

        prompt = str(captured[0][0].content)
        assert "进程调度" in prompt
        assert "调度器从就绪队列选择下一个运行的进程。" in prompt
        assert "重要度：5 / 5" in prompt
        assert "已修改名称" not in prompt
        assert "给我讲讲它" in [message.content for message in captured[1]]
        assert "再举个例子" in [message.content for message in captured[1]]

        listed = await client.get("/api/chat-sessions")
        assert listed.status_code == 200
        assert session_id in [item["id"] for item in listed.json()]


@pytest.mark.anyio
async def test_long_mounted_stream_reads_confirmed_assets_and_valid_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        app,
        client,
        captured,
    ):
        transcript = "长" * 30001 + "可核实摘录"
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]
        await send_message(client, session_id, "先提问")
        async with app.state.session_factory() as session, session.begin():
            for index, status in enumerate(("CONFIRMED", "GENERATED", "SUPERSEDED"), 1):
                session.add(
                    AiSummary(
                        record_id=record_id,
                        version_no=index,
                        transcript_source_version=1,
                        topic=f"主题{status}",
                        abstract=f"摘要{status}",
                        summary_json=json.dumps(
                            {"sections": [{"heading": "细节", "points": [f"要点{status}"]}]}
                        ),
                        status=status,
                        model="stub",
                        prompt_version="stub",
                        token_usage_json="{}",
                        latency_ms=0,
                    )
                )
            for status in ("ACTIVE", "DRAFT", "SUPERSEDED"):
                session.add(
                    KnowledgePoint(
                        record_id=record_id,
                        name=f"知识点{status}",
                        detail=f"完整详情{status}",
                        tags="[]",
                        importance=3,
                        generation_status=status,
                    )
                )
            await session.execute(
                update(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == ChatRole.ASSISTANT,
                )
                .values(
                    citations_json=json.dumps(
                        [
                            {"record_id": record_id, "quote": "可核实摘录"},
                            {"record_id": record_id, "quote": "不存在的摘录"},
                            {"record_id": "other-record", "quote": "长"},
                        ]
                    )
                )
            )
        assert (await send_message(client, session_id, "再问细节"))[-1][0] == "done"
        prompt = str(captured[1][0].content)
        assert transcript not in prompt
        assert "摘要CONFIRMED" in prompt and "要点CONFIRMED" in prompt
        assert "知识点ACTIVE" in prompt and "完整详情ACTIVE" in prompt
        assert "可核实摘录" in prompt and "不存在的摘录" not in prompt
        assert "GENERATED" not in prompt and "SUPERSEDED" not in prompt and "DRAFT" not in prompt
        async with app.state.session_factory() as session, session.begin():
            session.add_all(
                [
                    KnowledgePoint(
                        record_id=record_id,
                        name=f"补充知识点{index}",
                        detail="长" * 2000,
                        tags="[]",
                        importance=3,
                        generation_status="ACTIVE",
                    )
                    for index in range(31)
                ]
            )
        oversized = await send_message(client, session_id, "材料过长时不发送给模型")
        assert [event for event, _ in oversized] == ["status", "error"]
        # 新增资产改变来源版本，旧引用先失效，不能进入后续预算或模型请求。
        assert oversized[-1][1]["code"] == "CONTEXT_SOURCE_STALE"
        assert len(captured) == 2


@pytest.mark.anyio
async def test_send_message_streams_status_tokens_then_done_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        saved = await client.put(
            "/api/profile",
            json={"primary_role": "DEVELOPER", "about_me": "三年后端"},
        )
        assert saved.status_code == 200
        session_id = await create_session(client)

        events = await send_message(client, session_id, "什么是 MVCC")

        names = [name for name, _payload in events]
        assert names[0] == "status"
        assert names[1:-1] == ["token"] * (len(names) - 2)
        assert names[-1] == "done"
        assert events[0][1]["phase"] == "generating"
        tokens = [payload["text"] for name, payload in events if name == "token"]
        assert tokens == STUB_REPLY
        assert events[-1][1]["content"] == "回答完成了"

        # 用户与助手消息都落库；SYSTEM 快照仍在最前（角色在建档后创建的会话生效）。
        rows = await message_rows(tmp_path, session_id)
        assert rows[0][0] == "SYSTEM"
        assert "程序员" in rows[0][1]
        assert ("USER", "什么是 MVCC") in rows
        assert ("ASSISTANT", "回答完成了") in rows

        # 重开会话：历史接口完整返回，assistant 行带模型名。
        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assert history.status_code == 200
        body = history.json()
        assert [item["role"] for item in body] == ["SYSTEM", "USER", "ASSISTANT"]
        assert body[2]["model"] == "stub-chat-model"
        assert body[2]["content"] == "回答完成了"

        # 会话标题默认取首条用户消息。
        detail = await client.get(f"/api/chat-sessions/{session_id}")
        assert detail.json()["title"] == "什么是 MVCC"


@pytest.mark.anyio
async def test_context_contains_system_snapshot_and_all_completed_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 12) as (
        _app,
        client,
        captured,
    ):
        session_id = await create_session(client)

        for index in range(1, 12):
            events = await send_message(client, session_id, f"问题{index}")
            assert events[-1][0] == "done"

        # 第 11 次发送时历史恰有 10 个完成轮：SYSTEM 快照 + 10 轮 + 当前提问。
        eleventh = captured[10]
        assert eleventh[0].type == "system"
        assert "学习助手" in str(eleventh[0].content)
        contents = [str(message.content) for message in eleventh]
        assert "问题1" in contents and "问题10" in contents and "问题11" in contents
        assert contents.count("回答完成了") == 10
        assert len(eleventh) == 1 + 10 * 2 + 1

        # 未触发预算压缩时，超过十轮仍保留完整历史。
        await send_message(client, session_id, "问题12")
        contents = [str(message.content) for message in captured[11]]
        assert "问题1" in contents
        assert "问题2" in contents and "问题12" in contents
        assert contents.count("回答完成了") == 11


@pytest.mark.anyio
async def test_interrupted_stream_keeps_user_row_and_skips_assistant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """票 01：停止经持久取消指令落实（挂起中的生成被取消，不等待下一条 token）；
    部分输出已持久、user 行保留、无 assistant；取消释放会话，新问补答复用原行。"""
    release = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("回答",), release=release), list(STUB_REPLY)]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)
        turn_id = await submit_turn(client, session_id, "会被中断的问题")
        await wait_turn_progress(client, turn_id, min_seq=1)

        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["turn"]["cancel_requested"] is True
        final = await wait_turn_terminal(client, turn_id)
        assert final["status"] == "CANCELLED"
        release.set()

        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        process = next(item for item in history if item["role"] == "USER")["response_processes"][0]
        assert process["status"] == "INTERRUPTED"
        assert process["ended_at"] is not None

        rows = await message_rows(tmp_path, session_id)
        assert ("USER", "会被中断的问题") in rows
        assert all(role != "ASSISTANT" for role, _content in rows)

        # 中断释放了在途锁：同一会话可再次发送；补答复用原 user 行，无重复提问。
        events = await send_message(client, session_id, "会被中断的问题")
        assert events[-1][0] == "done"
        rows = await message_rows(tmp_path, session_id)
        assert [content for role, content in rows if role == "USER"].count("会被中断的问题") == 1
        assert ("ASSISTANT", "回答完成了") in rows

        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        processes = next(item for item in history if item["role"] == "USER")["response_processes"]
        assert [item["status"] for item in processes] == ["INTERRUPTED", "COMPLETED"]


@pytest.mark.anyio
async def test_second_send_while_streaming_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """票 01：同会话已有非终态轮次 → 409 明确冲突；不建隐藏队列、不覆盖已有
    USER 消息；停止（或完成）后才能新问。"""
    release = asyncio.Event()
    replies: list[StubReply] = [
        GatedReply(prefix=("正在",), release=release),
        list(STUB_REPLY),
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)
        turn_id = await submit_turn(client, session_id, "第一条")
        await wait_turn_progress(client, turn_id, min_seq=1)

        conflict = await client.post(
            f"/api/chat-sessions/{session_id}/turns",
            json={"content": "第二条", "web_search": False, "request_id": str(uuid4())},
        )
        assert conflict.status_code == 409
        assert "CHAT_TURN_IN_PROGRESS" in conflict.json()["detail"]
        # 冲突提交不落第二条 user 消息（不覆盖、不排队）。
        rows = await message_rows(tmp_path, session_id)
        assert ("USER", "第一条") in rows
        assert all(content != "第二条" for _role, content in rows)

        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        await wait_turn_terminal(client, turn_id)
        release.set()
        # 终态后新问创建新轮次。
        events = await send_message(client, session_id, "第二条")
        assert events[-1][0] == "done"


@pytest.mark.anyio
async def test_done_always_carries_memory_used_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """done 恒带 memory_used（工单 06）：零注入时为空数组，前端据其展示
    「本轮未使用任何记忆」空态，可区分「未询问」与「确认未注入」。"""
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        events = await send_message(client, session_id, "问题")
        done_event, done_payload = events[-1]
        assert done_event == "done"
        assert done_payload["memory_used"] == []


@pytest.mark.anyio
async def test_provider_failure_emits_error_and_chat_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[None, list(STUB_REPLY)]) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)

        events = await send_message(client, session_id, "第一次提问")
        assert events[0][0] == "status"
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "CHAT_STREAM_FAILED"
        assert events[-1][1]["process"]["status"] == "FAILED"
        assert not any(name == "done" for name, _payload in events)

        # 失败不落 assistant 行；error 后可继续发问并成功。
        rows = await message_rows(tmp_path, session_id)
        assert all(role != "ASSISTANT" for role, _content in rows)
        retry = await send_message(client, session_id, "第一次提问")
        assert retry[-1][0] == "done"
        rows = await message_rows(tmp_path, session_id)
        assert ("ASSISTANT", "回答完成了") in rows

        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        processes = next(item for item in history if item["role"] == "USER")["response_processes"]
        assert [item["status"] for item in processes] == ["FAILED", "COMPLETED"]
        assert processes[0]["id"] != processes[1]["id"]

        # 回答错误可区分（CB-08）：失败轮埋点带 CHAT_STREAM_FAILED，重试成功轮无错误码。
        logs = await chat_log_rows(tmp_path)
        assert [cast(str | None, row[5]) for row in logs] == ["CHAT_STREAM_FAILED", None]


@pytest.mark.anyio
async def test_llm_call_logs_records_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        await send_message(client, session_id, "记录埋点")

        rows = await chat_log_rows(tmp_path)
        assert len(rows) == 1
        graph_name, graph_node, model, prompt_version, token_usage_json, error_code = rows[0]
        assert (graph_name, graph_node, model) == (
            "chat",
            "generate",
            "stub-chat-model",
        )
        assert prompt_version
        assert "total_tokens" in cast(str, token_usage_json)
        assert error_code is None

        # 表结构不含对话正文的落点；日志记录只有元数据列（迁移 0008 定义的列集）。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            columns = {
                cast(str, item[1])
                for item in await (
                    await connection.execute("PRAGMA table_info(llm_call_logs)")
                ).fetchall()
            }
        assert columns == {
            "id",
            "request_id",
            "graph_name",
            "graph_node",
            "model",
            "prompt_version",
            "embedding_model",
            "token_usage_json",
            "latency_ms",
            "retrieval_count",
            "evidence_count",
            "interrupt_count",
            "error_code",
            "created_at",
        }


@pytest.mark.anyio
async def test_llm_call_logs_retrieval_count_and_no_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CB-08 观测性：retrieval_count 反映资料检索命中（None=未检索 / 0=检索无命中），
    且日志任何列都不含转写正文、用户提问或检索词。"""
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("search_library", {"query": "傅里叶"}),
            ["回答完成了"],
            list(STUB_REPLY),
            # 参数类型非法：工具执行失败（检索了但 0 命中）。
            ToolCallReply("search_library", {"query": 123}),
            list(STUB_REPLY),
        ],
    ) as (_app, client, _captured):
        imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "傅里叶笔记.txt",
                    "本讲系统梳理傅里叶级数的展开方法".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 202
        record_id = cast(str, imported.json()["record_id"])
        await wait_for_transcript_ready(client, record_id)
        mounted = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert mounted.status_code == 201
        mounted_id = cast(str, mounted.json()["id"])

        events = await send_message(client, mounted_id, "傅里叶级数怎么展开？")
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]

        free_id = await create_session(client)
        assert (await send_message(client, free_id, "自由提问"))[-1][0] == "done"

        failed = await send_message(client, mounted_id, "再检索一次")
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in failed
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 0, "ok": False}]
        assert failed[-1][0] == "done"

        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            rows = list(
                await (
                    await connection.execute(
                        "SELECT error_code, retrieval_count FROM llm_call_logs"
                        " WHERE graph_name = 'chat'"
                    )
                ).fetchall()
            )
        assert rows == [
            (None, 1),  # 挂载检索成功：命中合计
            (None, None),  # 自由聊天：未检索
            (None, 0),  # 检索失败：检索了但 0 命中（与未检索可区分）
        ]

        # 日志只有元数据：转写原文 / 用户提问 / 检索词不出现在任何列。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            log_rows = list(
                await (await connection.execute("SELECT * FROM llm_call_logs")).fetchall()
            )
        dump = "\n".join(str(value) for row in log_rows for value in row)
        assert "本讲系统梳理傅里叶级数的展开方法" not in dump
        assert "傅里叶" not in dump
        assert "自由提问" not in dump
        assert "再检索一次" not in dump


@pytest.mark.anyio
async def test_fts_exception_streams_failure_and_logs_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CB-08 检索错误归因：FTS 异常 → SSE 失败态 + loguru 告警 + 埋点 0 命中，流不断。"""

    async def _fts_down(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("fts index unavailable")

    # 工单 04 起检索统一走 LibraryRetrievalService（seam 收编，
    # SegmentSearchService 不再位于工具路径上）。
    monkeypatch.setattr(LibraryRetrievalService, "search", _fts_down)
    logs = StringIO()
    sink_id = logger.add(logs, format="{message} {extra}", level="WARNING")
    try:
        async with streaming_chat_app(
            tmp_path,
            monkeypatch,
            replies=[ToolCallReply("search_library", {"query": "傅里叶"}), list(STUB_REPLY)],
        ) as (_app, client, _captured):
            capture = await client.post(
                "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "原文"}
            )
            record_id = cast(str, capture.json()["record_id"])
            created = await client.post("/api/chat-sessions", json={"record_id": record_id})
            session_id = cast(str, created.json()["id"])

            events = await send_message(client, session_id, "检索一下")
    finally:
        logger.remove(sink_id)

    assert [
        {key: payload[key] for key in ("tool", "hits", "ok")}
        for name, payload in events
        if name == "tool_result"
    ] == [{"tool": "search_library", "hits": 0, "ok": False}]
    assert events[-1][0] == "done"
    warnings = [line for line in logs.getvalue().splitlines() if "chat_tool_failed" in line]
    assert len(warnings) == 1 and "'tool': 'search_library'" in warnings[0]

    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        row = await (
            await connection.execute(
                "SELECT error_code, retrieval_count FROM llm_call_logs WHERE graph_name = 'chat'"
            )
        ).fetchone()
    assert row is not None and (row[0], row[1]) == (None, 0)


@pytest.mark.anyio
async def test_send_without_provider_returns_semantic_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", StubChatModel)
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            session_id = await create_session(client)
            response = await client.post(
                f"/api/chat-sessions/{session_id}/turns",
                json={"content": "没配置供应商", "web_search": False, "request_id": "req-nopro-1"},
            )
            assert response.status_code == 409
            assert "LLM_PROVIDER_UNCONFIGURED" in response.json()["detail"]
            rows = await message_rows(tmp_path, session_id)
            assert all(role != "USER" for role, _content in rows)


@pytest.mark.anyio
async def test_send_validates_payload_and_missing_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        blank = await client.post(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000001/turns",
            json={"content": "   ", "web_search": False, "request_id": "req-blank-001"},
        )
        assert blank.status_code == 422

        no_request_id = await client.post(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000001/turns",
            json={"content": "缺少请求身份"},
        )
        assert no_request_id.status_code == 422

        missing = await client.post(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000002/turns",
            json={"content": "不存在的会话", "web_search": False, "request_id": "req-miss-001"},
        )
        assert missing.status_code == 404

        history_missing = await client.get(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000002/messages"
        )
        assert history_missing.status_code == 404


@pytest.mark.anyio
async def test_mounted_reply_citations_validated_stripped_and_streamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = "数据库的 MVCC 依赖 undo 日志实现多版本读，写入时保留旧版本。"
    reply = [
        "MVCC 依赖 undo 日志[1]。",
        "\n[1] 数据库的 MVCC 依赖 undo 日志实现多版本读",
        "\n[2] 转写中不存在的摘录",
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[reply]) as (
        _app,
        client,
        captured,
    ):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "MVCC 怎么实现？")

        # 挂载提示词带引用约定。
        assert "角标" in str(captured[0][0].content)
        names = [name for name, _payload in events]
        assert names == ["status", "token", "token", "token", "citation", "done"]
        # 子串校验：转写中不存在的摘录整条丢弃，不下发、不落库。
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "quote": "数据库的 MVCC 依赖 undo 日志实现多版本读",
            }
        ]
        assert events[-1][1]["content"] == "MVCC 依赖 undo 日志[1]。"

        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["content"] == "MVCC 依赖 undo 日志[1]。"
        assert assistant["citations"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "record_title": None,
                "quote": "数据库的 MVCC 依赖 undo 日志实现多版本读",
                "url": None,
                "title": None,
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            }
        ]
        assert "citations_json" not in assistant


@pytest.mark.anyio
async def test_mounted_blockquote_paraphrase_citation_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = (
        "Docker 是一个用于开发、交付和运行应用程序的开放平台。\n"
        "Docker 使您能够将应用程序与基础架构分离。"
    )
    # 模型真实劣化形态：引用块带 markdown 前缀 + 摘录为意译改写。
    reply = [
        "Docker 是容器化平台[1]。",
        "\n> [1] Docker是用于开发、交付和运行应用程序的开放平台，使应用与基础架构分离。",
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[reply]) as (
        _app,
        client,
        captured,
    ):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "Docker 是什么？")

        # 提示词明确禁止 markdown 前缀（格式加固）。
        assert "不要使用 >、- 等 markdown 前缀" in str(captured[0][0].content)
        names = [name for name, _payload in events]
        assert names == ["status", "token", "token", "citation", "done"]
        # blockquote 引用块被识别剥离；意译摘录对齐为真实原句下发。
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "quote": "Docker 是一个用于开发、交付和运行应用程序的开放平台。",
            }
        ]
        assert events[-1][1]["content"] == "Docker 是容器化平台[1]。"

        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "record_title": None,
                "quote": "Docker 是一个用于开发、交付和运行应用程序的开放平台。",
                "url": None,
                "title": None,
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            }
        ]


@pytest.mark.anyio
async def test_free_chat_reply_produces_no_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reply = ["普通回答[1]。\n[1] 看起来像引用的一行"]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[reply]) as (
        _app,
        client,
        captured,
    ):
        session_id = await create_session(client)
        events = await send_message(client, session_id, "自由聊天")

        # 自由聊天提示词不带引用约定，回复原文保留、不产出引用。
        assert "角标" not in str(captured[0][0].content)
        assert not any(name == "citation" for name, _payload in events)
        assert events[-1][1]["content"] == "普通回答[1]。\n[1] 看起来像引用的一行"

        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"] == []
        assert assistant["content"] == "普通回答[1]。\n[1] 看起来像引用的一行"


class _SkeletonProbeModel(BaseChatModel):
    """空骨架探测缝隙：记录 bind_tools 收到的工具名与模型实际收到的 system 消息。

    ClassVar 共享沿用 StubChatModel 模式；每次测试前手动重置。
    """

    bound_tools: ClassVar[list[str] | None] = None
    seen_system: ClassVar[str | None] = None

    @property
    def _llm_type(self) -> str:
        return "skeleton-probe"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_SkeletonProbeModel":
        type(self).bound_tools = [getattr(t, "name", "?") for t in tools]
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        type(self).seen_system = cast(
            "str | None",
            next(
                (m.content for m in messages if isinstance(m, SystemMessage)),
                None,
            ),
        )
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="骨架等价探测回复"))]
        )


class TestDeepagentsEmptySkeleton:
    """ADR-0018 空骨架等价闸门：模型可见工具面为空、system 提示经参数注入完整到达。

    兼作 deepagents 升级的回归闸门——升级后内置工具名或提示注入行为变化即红。
    """

    def test_model_sees_empty_toolset_and_param_system_prompt(self) -> None:
        _SkeletonProbeModel.bound_tools = None
        _SkeletonProbeModel.seen_system = None
        agent = build_chat_agent(
            _SkeletonProbeModel(),
            InMemorySaver(),
            system_prompt=SystemMessage(content="你是学习助手"),
        )
        result = agent.invoke(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            {"messages": [HumanMessage(content="你好")]},
            config={"configurable": {"thread_id": "skeleton-probe"}},
        )
        assert result["messages"][-1].content == "骨架等价探测回复"
        # 空工具面：bind_tools 未被调用或收到空列表（deepagents 内置工具全部不可见）。
        assert _SkeletonProbeModel.bound_tools in (None, [])
        # system 提示经参数注入完整到达（deepagents 会丢弃混入 messages 的 SystemMessage）。
        assert _SkeletonProbeModel.seen_system == "你是学习助手"


@pytest.mark.anyio
async def test_mounted_tool_call_searches_segments_and_streams_tool_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final_reply = [
        "傅里叶级数用三角函数的和表示周期函数[1]。",
        "\n[1] 本讲系统梳理傅里叶级数的展开方法",
    ]
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": "傅里叶"}), final_reply],
    ) as (_app, client, captured):
        imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "傅里叶笔记.txt",
                    "本讲系统梳理傅里叶级数的展开方法".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 202
        record_id = cast(str, imported.json()["record_id"])
        await wait_for_transcript_ready(client, record_id)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "傅里叶级数怎么展开？")

        names = [name for name, _payload in events]
        assert names[0] == "status"
        assert names[-1] == "done"
        assert names.index("tool_call") < names.index("tool_result") < names.index("token")
        assert [
            {key: payload[key] for key in ("tool", "query")}
            for name, payload in events
            if name == "tool_call"
        ] == [{"tool": "search_library", "query": "傅里叶"}]
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]
        # 工具命中进入第二次模型调用的上下文（ToolMessage 逐字原文）。
        tool_messages = [message for message in captured[1] if isinstance(message, ToolMessage)]
        assert len(tool_messages) == 1
        assert "本讲系统梳理傅里叶级数的展开方法" in str(tool_messages[0].content)
        # 命中句被模型逐字引用：citation 完整下发并落库。
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "quote": "本讲系统梳理傅里叶级数的展开方法",
            }
        ]
        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "record_title": None,
                "quote": "本讲系统梳理傅里叶级数的展开方法",
                "url": None,
                "title": None,
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            }
        ]

        # token 用量跨工具循环两次模型调用累加（stub 每次输入 3 / 输出 4 / 合计 7）。
        rows = await chat_log_rows(tmp_path)
        assert len(rows) == 1
        assert rows[0][3] == "chat-library-scope-v39"
        usage = json.loads(cast(str, rows[0][4]))
        assert usage == {"input_tokens": 6, "output_tokens": 8, "total_tokens": 14}


@pytest.mark.anyio
async def test_mounted_tool_falls_back_to_substring_without_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = "第一段讲缓存淘汰策略。\n第二段讲一致性哈希。"
    final_reply = ["一致性哈希把节点映射到环上[1]。", "\n[1] 第二段讲一致性哈希。"]
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[
            # args 分片流式到达：未闭合 JSON 不得提前上报截断的「一致」。
            ToolCallReply(
                "search_library",
                {"query": "一致性哈希"},
                args_fragments=('{"query": "一致', '性哈希"}'),
            ),
            final_reply,
        ],
    ) as (_app, client, captured):
        # 粘贴/速记记录无分片：检索退化为全文子串兜底。
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        assert capture.status_code == 201
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "一致性哈希是什么？")

        assert [
            {key: payload[key] for key in ("tool", "query")}
            for name, payload in events
            if name == "tool_call"
        ] == [{"tool": "search_library", "query": "一致性哈希"}]
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]
        tool_messages = [message for message in captured[1] if isinstance(message, ToolMessage)]
        assert len(tool_messages) == 1
        assert "第二段讲一致性哈希。" in str(tool_messages[0].content)
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "quote": "第二段讲一致性哈希。",
            }
        ]
        # ≤30k 挂载不追加检索工具指引（全文已在上下文，工具闲置）。
        assert "search_library" not in str(captured[0][0].content)


@pytest.mark.anyio
async def test_agent_short_query_supplements_segmented_record_fts_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": "MVC"}), list(STUB_REPLY)],
    ) as (_app, client, _captured):
        imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "MVCC笔记.txt",
                    "MVCC 依赖 undo 日志实现多版本读".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 202
        record_id = cast(str, imported.json()["record_id"])
        await wait_for_transcript_ready(client, record_id)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "MVC 是什么？")

        # Agent 短主题补充：即使非 FTS 整词，仍能以同范围逐字子串取得真实原文。
        assert "MVC" in "MVCC 依赖 undo 日志实现多版本读"
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]


@pytest.mark.anyio
async def test_long_mounted_prompt_adds_retrieval_tool_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = "长" * 30001 + "可检索细节"
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, captured):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        assert (await send_message(client, session_id, "细节问题"))[-1][0] == "done"

        # >30k 降级材料追加检索工具指引；工具描述对模型可见。
        prompt = str(captured[0][0].content)
        assert "search_library" in prompt
        assert "缺失细节不可推断" in prompt


@pytest.mark.anyio
async def test_mounted_tool_failure_streams_failed_tool_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 参数类型非法：工具执行失败落在 ToolNode 错误 ToolMessage，SSE 如实下发失败态。
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": 123}), list(STUB_REPLY)],
    ) as (_app, client, _captured):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "原文"}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "检索一下")

        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 0, "ok": False}]
        assert events[-1][0] == "done"


# ---------------------------------------------------------------------------
# B1 联网搜索：装配矩阵（挂载 × web_search 标志 × 有/无 key）、工具事件、
# 网络引用分流与提示注入契约。
# ---------------------------------------------------------------------------


class BindRecordingModel(StubChatModel):
    """装配矩阵探针：记录 bind_tools 收到的工具名列表（每次断言前重置）。"""

    bound: ClassVar[list[str]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> "BindRecordingModel":
        type(self).bound = [getattr(t, "name", "?") for t in tools]
        return self


def tavily_payload(*titles: str) -> dict[str, Any]:
    return {
        "results": [
            {"title": title, "url": f"https://example.com/{title}", "content": f"{title} 的内容"}
            for title in titles
        ]
    }


def patch_tavily_transport(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.AsyncBaseTransport
) -> None:
    class _TransportedTavily(TavilySearchClient):
        def __init__(self, api_key: str) -> None:
            super().__init__(api_key, transport=transport)

    monkeypatch.setattr("app.modules.agent.turns.worker.TavilySearchClient", _TransportedTavily)


def test_cited_excerpts_skip_web_entries() -> None:
    raw = json.dumps(
        [
            {"index": 1, "source": "record", "record_id": "r1", "quote": "摘录甲"},
            {"index": 2, "source": "web", "url": "https://example.com", "title": "网页"},
        ]
    )
    # 长转写回喂摘录按 record_id 过滤，web 条目天然排除。
    assert _cited_excerpts(raw, "r1") == ("摘录甲",)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.anyio
async def test_web_search_mounting_matrix_tool_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", BindRecordingModel)
    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
        model_budget=ModelBudgetConfig(context_window=128000),
    )
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            capture = await client.post(
                "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "材料原文"}
            )
            record_id = capture.json()["record_id"]
            free_id = await create_session(client)
            created = await client.post("/api/chat-sessions", json={"record_id": record_id})
            assert created.status_code == 201
            mounted_id = created.json()["id"]
            BindRecordingModel.replies = [list(STUB_REPLY)] * 12

            async def visible(session_id: str, *, web: bool) -> list[str]:
                BindRecordingModel.bound = []
                events = await send_message(client, session_id, "问题", web_search=web)
                assert events[-1][0] == "done"
                return list(BindRecordingModel.bound)

            # 无 key：标志开启也被后端无视（双保险），自由与挂载都不出现 web_search。
            assert "web_search" not in await visible(free_id, web=True)
            assert "web_search" not in await visible(mounted_id, web=True)
            assert "search_library" in await visible(mounted_id, web=True)

            save_web_search_provider(
                tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
            )

            # 有 key：标志开关精确控制挂载；挂载会话两工具并存。
            assert "web_search" in await visible(free_id, web=True)
            assert "web_search" not in await visible(free_id, web=False)
            assert "search_library" not in await visible(free_id, web=False)
            assert "web_search" in await visible(mounted_id, web=True)
            assert "search_library" in await visible(mounted_id, web=True)
            assert "web_search" not in await visible(mounted_id, web=False)
            assert "search_library" in await visible(mounted_id, web=False)


@pytest.mark.anyio
async def test_free_chat_web_search_streams_tool_events_and_web_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tavily_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tavily_requests.append(request)
        return httpx.Response(200, json=tavily_payload("Python 3.13", "PEP 604"))

    final_reply = [
        "Python 3.13 已发布[1]。",
        "\n[1] Python 官网 — https://www.python.org/downloads/",
    ]
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("web_search", {"query": "Python 最新版本"}), final_reply],
    ) as (_app, client, captured):
        patch_tavily_transport(monkeypatch, httpx.MockTransport(handler))
        save_web_search_provider(
            tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
        )
        session_id = await create_session(client)

        events = await send_message(client, session_id, "Python 最新版本是多少？", web_search=True)

        # 联网指引进入 system 提示（自由聊天无挂载限定句）。
        prompt = str(captured[0][0].content)
        assert "web_search 工具联网查询" in prompt
        assert "retryable=false" in prompt
        assert "不要更换查询词或再次调用" in prompt
        assert "[n] 标题 — URL" in prompt
        assert "仅作为材料外的补充来源" not in prompt

        names = [name for name, _payload in events]
        assert names[0] == "status" and names[-1] == "done"
        assert names.index("tool_call") < names.index("tool_result") < names.index("token")
        assert [
            {key: payload[key] for key in ("tool", "query")}
            for name, payload in events
            if name == "tool_call"
        ] == [{"tool": "web_search", "query": "Python 最新版本"}]
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "web_search", "hits": 2, "ok": True}]
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "web",
                "url": "https://www.python.org/downloads/",
                "title": "Python 官网",
            }
        ]
        assert events[-1][1]["content"] == "Python 3.13 已发布[1]。"

        # Tavily 请求形态：单端点 REST、Bearer key、top-5。
        request = tavily_requests[0]
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["Authorization"] == "Bearer tvly-test"
        assert json.loads(request.content) == {"query": "Python 最新版本", "max_results": 5}

        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"] == [
            {
                "index": 1,
                "source": "web",
                "record_id": None,
                "record_title": None,
                "quote": None,
                "url": "https://www.python.org/downloads/",
                "title": "Python 官网",
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            }
        ]


@pytest.mark.anyio
async def test_web_search_failure_streams_failed_tool_result_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("web_search", {"query": "最新动态"}), list(STUB_REPLY)],
    ) as (_app, client, _captured):
        patch_tavily_transport(monkeypatch, httpx.MockTransport(handler))
        save_web_search_provider(
            tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
        )
        session_id = await create_session(client)

        events = await send_message(client, session_id, "外发查询", web_search=True)

        # 网络失败：错误 JSON 载荷 → tool_result 失败态，流不中断、回答照常完成。
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "web_search", "hits": 0, "ok": False}]
        assert events[-1][0] == "done"
        assert not any(name == "error" for name, _payload in events)


@pytest.mark.anyio
async def test_mounted_web_flag_citations_mix_record_and_web_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = "数据库的 MVCC 依赖 undo 日志实现多版本读，写入时保留旧版本。"
    reply = [
        "MVCC 靠 undo 日志实现[1]，最新动态见官方博客[2]。",
        "\n[1] 数据库的 MVCC 依赖 undo 日志实现多版本读",
        "\n[2] MVCC 博客 — https://example.com/mvcc",
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[reply]) as (
        _app,
        client,
        captured,
    ):
        save_web_search_provider(
            tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
        )
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "MVCC 怎么实现？", web_search=True)

        # 挂载会话联网指引带「材料优先、网络补充」语义。
        assert "仅作为材料外的补充来源" in str(captured[0][0].content)
        # 混合引用块：转写条目逐字校验照旧，网络条目不校验，两者并存分流。
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "quote": "数据库的 MVCC 依赖 undo 日志实现多版本读",
            },
            {"index": 2, "source": "web", "url": "https://example.com/mvcc", "title": "MVCC 博客"},
        ]

        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "record_title": None,
                "quote": "数据库的 MVCC 依赖 undo 日志实现多版本读",
                "url": None,
                "title": None,
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            },
            {
                "index": 2,
                "source": "web",
                "record_id": None,
                "record_title": None,
                "quote": None,
                "url": "https://example.com/mvcc",
                "title": "MVCC 博客",
                "library_item_id": None,
                "anchor_id": None,
                "shared": None,
            },
        ]


@pytest.mark.anyio
async def test_prompt_byte_identical_when_web_search_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, captured):
        save_web_search_provider(
            tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
        )
        session_id = await create_session(client)
        await send_message(client, session_id, "问题")

        # 关闭标志：提示与现状逐字一致（中性快照 + 时间提示行 + 枚举/批量指引 +
        # 语言指令，无联网指引）。时间提示行含动态时间戳（时间能力 v1），单独
        # 剥离断言形状，其余部分保持逐字比对。
        role_line, time_line, rest = captured[0][0].text.split("\n", 2)
        rest = rest.split("\n本执行工具额度：", 1)[0]
        assert role_line == "你是 KnowRealm 学习助手。用户尚未建立档案，请以中性、通用的语气回答。"
        assert time_line.startswith("时间提示：当前时间 ")
        assert "get_current_time" in time_line
        assert rest == (
            f"{CHAT_ENUMERATION_GUIDANCE}\n"
            f"{CHAT_BATCH_PLAN_GUIDANCE}\n"
            f"{CHAT_UNDO_GUIDANCE}\n"
            f"{CHAT_GOAL_GUIDANCE}\n"
            f"{CHAT_PLAN_GUIDANCE}\n"
            f"{CHAT_SHARED_REF_GUIDANCE}\n"
            f"{CHAT_RUN_BINDING_GUIDANCE}\n"
            f"{CHAT_LANGUAGE_INSTRUCTION}"
        )

        # 挂载会话同样只在标志开启时注入联网指引。
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "材料原文"}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert created.status_code == 201
        mounted_id = created.json()["id"]
        await send_message(client, mounted_id, "挂载问题")
        assert "web_search 工具联网查询" not in str(captured[1][0].content)


# ---------------------------------------------------------------------------
# B2 跨记录问答：scope 装配矩阵（FREE/RECORD/COURSE|ALL × web_search）、
# search_library 工具事件、清单注入与跨记录引用落库。
# ---------------------------------------------------------------------------


async def create_course_for_scope(client: httpx.AsyncClient, name: str = "分布式系统") -> str:
    created = await client.post(
        "/api/courses", json={"name": name, "learning_context": "INTEREST", "depth": "BEGINNER"}
    )
    assert created.status_code == 201
    return cast(str, created.json()["id"])


async def record_id_by_title(client: httpx.AsyncClient, title: str) -> str:
    options = await client.get("/api/chat-sessions/record-options")
    assert options.status_code == 200
    return cast(str, next(item["id"] for item in options.json() if item["title"] == title))


@pytest.mark.anyio
async def test_scope_mounting_matrix_tool_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", BindRecordingModel)
    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
        model_budget=ModelBudgetConfig(context_window=128000),
    )
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            course_id = await create_course_for_scope(client)
            capture = await client.post(
                "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "材料原文"}
            )
            record_id = capture.json()["record_id"]
            free_id = await create_session(client)
            record_created = await client.post("/api/chat-sessions", json={"record_id": record_id})
            assert record_created.status_code == 201
            record_session_id = record_created.json()["id"]
            course_created = await client.post(
                "/api/chat-sessions", json={"scope": "COURSE", "course_id": course_id}
            )
            assert course_created.status_code == 201
            course_session_id = course_created.json()["id"]
            all_created = await client.post("/api/chat-sessions", json={"scope": "ALL"})
            assert all_created.status_code == 201
            all_session_id = all_created.json()["id"]
            BindRecordingModel.replies = [list(STUB_REPLY)] * 8

            async def visible(session_id: str, *, web: bool = False) -> list[str]:
                BindRecordingModel.bound = []
                events = await send_message(client, session_id, "问题", web_search=web)
                assert events[-1][0] == "done"
                return list(BindRecordingModel.bound)

            # 检索工具按 scope 互斥挂载：FREE 无、RECORD=transcript、COURSE/ALL=library；
            # search_courses / list_course_records / list_library_items / 时间工具族
            # 四工具（时间能力 v1，恒挂载）/ list_goals /
            # get_goal（第三阶段工单 01 目标查询）/ propose_memory
            # / create_course / add_text_record_to_course 恒挂载（工单 01 操作工具组 /
            # 插队票 08 对象枚举 / 02 课程创建提案 / 03 文本记录提案 / 工单 06 任意
            # 会话支持用户明确「记住…」）
            # + 修改与归档动作六工具（工单 03'：update/archive/restore_course 与
            # update/archive/restore_library_item）+ 删除与迁移三工具（工单 04：
            # soft_delete_record / delete_course / move_record_course）+ 批量整理
            # 计划工具（工单 05：plan_batch_operations）+ 学习目标四工具与计划
            # 三工具（第三阶段工单 01/02，顺序 = 装配段）。
            assert await visible(free_id) == [
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]
            assert await visible(record_session_id) == [
                "search_library",
                "delegate_knowledge",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]
            assert await visible(course_session_id) == [
                "search_library",
                "delegate_knowledge",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]
            assert await visible(all_session_id) == [
                "search_library",
                "delegate_knowledge",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]

            # web_search 生效时在各 scope 基础上追加（需已配置 key）。
            save_web_search_provider(
                tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
            )
            assert await visible(course_session_id, web=True) == [
                "search_library",
                "delegate_knowledge",
                "web_search",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]
            assert await visible(all_session_id, web=True) == [
                "search_library",
                "delegate_knowledge",
                "web_search",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]
            assert await visible(record_session_id, web=True) == [
                "search_library",
                "delegate_knowledge",
                "web_search",
                "search_context",
                "read_context",
                "get_context_settings",
                "change_context_pin",
                "change_context_rules",
                "list_context_history",
                "search_courses",
                "list_course_records",
                "list_library_items",
                "get_current_time",
                "convert_time",
                "shift_datetime",
                "diff_datetime",
                "list_goals",
                "list_recent_learning",
                "list_recent_assets",
                "get_today_progress",
                "get_goal",
                "get_plan",
                "get_plan_practice",
                "get_plan_study",
                "confirm_practice_requirements",
                "prepare_plan_practice",
                "cancel_practice_preparation",
                "start_plan_practice",
                "retry_plan_practice_grading",
                "generate_learning_plan",
                "propose_memory",
                "create_course",
                "add_text_record_to_course",
                "update_course",
                "archive_course",
                "restore_course",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "soft_delete_record",
                "delete_course",
                "move_record_course",
                "plan_batch_operations",
                "wait_for_task",
                "undo_operation",
                "create_goal",
                "update_goal",
                "confirm_plan",
                "update_plan_item",
                "complete_plan_item",
                "regenerate_plan",
                "list_shared_refs",
                "add_shared_ref",
                "remove_shared_ref",
            ]


@pytest.mark.anyio
async def test_course_session_streams_library_tool_and_cross_record_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final_reply = [
        "第 2 讲更强调实践[1]。",
        "\n[1] 第二讲聚焦一致性哈希的实践应用（来源：第 2 讲 一致性哈希）",
    ]
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": "一致性哈希"}), final_reply],
    ) as (_app, client, captured):
        course_id = await create_course_for_scope(client)
        # 文档导入带分片索引：search_library 经 FTS 命中（工单 04 起 COURSE/ALL
        # 不再做 LIKE 兜底，粘贴/速记类无分片记录不进检索面）。
        first_imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "第 2 讲 一致性哈希.txt",
                    "第二讲聚焦一致性哈希的实践应用。".encode(),
                    "text/plain",
                )
            },
            data={"course_id": course_id},
        )
        second_imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "第 5 讲 分布式共识.txt",
                    "第五讲聚焦共识协议 Raft 的理论证明。".encode(),
                    "text/plain",
                )
            },
            data={"course_id": course_id},
        )
        assert first_imported.status_code == 202 and second_imported.status_code == 202
        await wait_for_transcript_ready(client, cast(str, first_imported.json()["record_id"]))
        await wait_for_transcript_ready(client, cast(str, second_imported.json()["record_id"]))
        created = await client.post(
            "/api/chat-sessions", json={"scope": "COURSE", "course_id": course_id}
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "对比一下两次课？")

        # 清单注入：课程范围 + 标题行 + 检索指引 + 跨记录引用格式；无角色快照。
        prompt = str(captured[0][0].content)
        assert "课程「分布式系统」" in prompt
        assert "共 2 条学习记录" in prompt
        assert "第 2 讲 一致性哈希（" in prompt
        assert "search_library" in prompt
        assert "（来源：来源标题）" in prompt

        names = [name for name, _payload in events]
        assert names[0] == "status" and names[-1] == "done"
        assert names.index("tool_call") < names.index("tool_result") < names.index("token")
        assert [
            {key: payload[key] for key in ("tool", "query")}
            for name, payload in events
            if name == "tool_call"
        ] == [{"tool": "search_library", "query": "一致性哈希"}]
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]
        # 工具命中进入第二次模型调用：跨记录命中带标题与逐字原文。
        tool_messages = [message for message in captured[1] if isinstance(message, ToolMessage)]
        assert len(tool_messages) == 1
        assert "第 2 讲 一致性哈希" in str(tool_messages[0].content)
        assert "第二讲聚焦一致性哈希的实践应用" in str(tool_messages[0].content)

        # 跨记录引用：归属由校验器裁定，落 record_id + record_title 快照。
        cited_record_id = await record_id_by_title(client, "第 2 讲 一致性哈希")
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": cited_record_id,
                "record_title": "第 2 讲 一致性哈希",
                "quote": "第二讲聚焦一致性哈希的实践应用",
            }
        ]
        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assistant = next(item for item in history.json() if item["role"] == "ASSISTANT")
        assert assistant["citations"][0]["record_title"] == "第 2 讲 一致性哈希"


@pytest.mark.anyio
async def test_library_item_session_injects_item_content_and_closes_citation_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 资料导入后「AI 解读」直接读到正文：LIBRARY_ITEM 会话 system 注入挂载条目
    # 转写正文（【来源：标题】段头），概览类提问不再依赖 FTS 检索命中；模型引用
    # 注入正文摘录时经同源校验材料逐字校验闭环。
    final_reply = [
        "这份笔记围绕傅里叶级数展开[1]。",
        "\n[1] 本讲系统梳理傅里叶级数的展开方法（来源：傅里叶笔记）",
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[final_reply]) as (
        _app,
        client,
        captured,
    ):
        accepted = await client.post(
            "/api/library/ingest",
            json={
                "source": "text",
                "title": "傅里叶笔记",
                "content": "本讲系统梳理傅里叶级数的展开方法",
            },
        )
        assert accepted.status_code == 202
        item_id = accepted.json()["item"]["id"]
        detail = await client.get(f"/api/library/items/{item_id}")
        record_id = detail.json()["derived_records"][0]["record_id"]

        created = await client.post(
            "/api/chat-sessions", json={"scope": "LIBRARY_ITEM", "library_item_id": item_id}
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "这份资料讲了什么？")

        prompt = str(captured[0][0].content)
        assert "资料正文（优先依据正文回答" in prompt
        assert "【来源：傅里叶笔记】" in prompt
        assert "本讲系统梳理傅里叶级数的展开方法" in prompt
        names = [name for name, _payload in events]
        assert names[0] == "status" and names[-1] == "done"
        assert "tool_call" not in names
        assert [payload for name, payload in events if name == "citation"] == [
            {
                "index": 1,
                "source": "record",
                "record_id": record_id,
                "record_title": "傅里叶笔记",
                "quote": "本讲系统梳理傅里叶级数的展开方法",
            }
        ]


@pytest.mark.anyio
async def test_library_item_content_over_budget_degrades_to_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 条目正文超过 30000 字符降级为清单 + 检索模式（对齐 RECORD 档 >30k 分支）。
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[["资料较长，建议检索。"]]) as (
        _app,
        client,
        captured,
    ):
        accepted = await client.post(
            "/api/library/ingest",
            json={"source": "text", "title": "长文", "content": "长" * 30001},
        )
        assert accepted.status_code == 202
        created = await client.post(
            "/api/chat-sessions",
            json={"scope": "LIBRARY_ITEM", "library_item_id": accepted.json()["item"]["id"]},
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "讲了什么？")

        prompt = str(captured[0][0].content)
        assert "资料正文（优先依据正文回答" not in prompt
        assert "共 1 条学习记录" in prompt
        assert "search_library" in prompt
        assert [name for name, _payload in events][-1] == "done"


@pytest.mark.anyio
async def test_library_item_without_content_states_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 无可用正文（解析/转写未完成或失败）：注入「尚未就绪」提示替代误导性「未找到」。
    async with streaming_chat_app(
        tmp_path, monkeypatch, replies=[["资料正文尚未就绪，请稍后再试。"]]
    ) as (_app, client, captured):
        accepted = await client.post(
            "/api/library/ingest",
            json={"source": "text", "title": "处理中资料", "content": "临时正文"},
        )
        assert accepted.status_code == 202
        item_id = accepted.json()["item"]["id"]
        # 模拟正文未就绪：软删 transcript（与加载器 deleted_at 过滤同口径）。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            await connection.execute("UPDATE transcripts SET deleted_at = '2026-09-19T00:00:00'")
            await connection.commit()

        created = await client.post(
            "/api/chat-sessions", json={"scope": "LIBRARY_ITEM", "library_item_id": item_id}
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "这份资料讲了什么？")

        prompt = str(captured[0][0].content)
        assert "暂无可用正文" in prompt
        assert "尚未就绪" in prompt
        assert [name for name, _payload in events][-1] == "done"


@pytest.mark.anyio
async def test_all_session_fts_library_hits_and_web_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": "傅里叶"}), list(STUB_REPLY)],
    ) as (_app, client, captured):
        save_web_search_provider(
            tmp_path, provider="tavily", api_key="tvly-test", clear_api_key=False
        )
        imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "傅里叶笔记.txt",
                    "本讲系统梳理傅里叶级数的展开方法".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 202
        record_id = cast(str, imported.json()["record_id"])
        await wait_for_transcript_ready(client, record_id)
        created = await client.post("/api/chat-sessions", json={"scope": "ALL"})
        assert created.status_code == 201
        session_id = created.json()["id"]

        events = await send_message(client, session_id, "傅里叶级数？", web_search=True)

        # 全部范围清单 + 联网指引带材料优先语义。
        prompt = str(captured[0][0].content)
        assert "全部资料" in prompt
        assert "仅作为材料外的补充来源" in prompt
        # 有分片记录命中 FTS（文档导入建分片）。
        assert [
            {key: payload[key] for key in ("tool", "hits", "ok")}
            for name, payload in events
            if name == "tool_result"
        ] == [{"tool": "search_library", "hits": 1, "ok": True}]
        tool_messages = [message for message in captured[1] if isinstance(message, ToolMessage)]
        assert len(tool_messages) == 1
        assert "本讲系统梳理傅里叶级数的展开方法" in str(tool_messages[0].content)


# ---------------------------------------------------------------------------
# search_library 概念增强与范围语义（工单 04 起消费 LibraryRetrievalService）。
# ---------------------------------------------------------------------------


async def seed_library_course(app: FastAPI, course_id: str, name: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, status, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :name, 'INTEREST', 'BEGINNER', 'ACTIVE', :now, :now, NULL)"
            ),
            {"id": course_id, "name": name, "now": NOW},
        )


async def seed_library_transcript(
    app: FastAPI,
    *,
    record_id: str,
    course_id: str,
    title: str,
    segment_id: str,
    content: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    """直插带转写分片的记录并同步分片索引（概念扩展命中的数据地基）。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'RECORDING', :title, 'COMPLETED', 60000, "
                ":now, :now, NULL)"
            ),
            {"id": record_id, "course_id": course_id, "title": title, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', 'audio/ogg', "
                "1, 60000, 0, 'h', :now, :now, NULL)"
            ),
            {"id": f"file-{segment_id}", "record_id": record_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)"
            ),
            {
                "id": f"transcript-{segment_id}",
                "record_id": record_id,
                "content": content,
                "now": NOW,
            },
        )
        await session.execute(
            text(
                "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                "speaker, content, content_hash) "
                "VALUES (:id, :transcript_id, :record_id, :file_id, 0, "
                ":start_ms, :end_ms, :start_ms, :end_ms, NULL, :content, :content_hash)"
            ),
            {
                "id": segment_id,
                "transcript_id": f"transcript-{segment_id}",
                "record_id": record_id,
                "file_id": f"file-{segment_id}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "content": content,
                "content_hash": content_hash(content),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, [segment_id]
        )


async def seed_library_concept(
    app: FastAPI,
    *,
    concept_id: str,
    course_id: str,
    name: str,
    description: str = "",
    status: str = "CONFIRMED",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                "description, concept_type, importance, status, source, created_at, updated_at) "
                "VALUES (:id, :course_id, :name, :normalized, :description, 'TERM', 3, "
                ":status, 'AI_EXTRACTED', :now, :now)"
            ),
            {
                "id": concept_id,
                "course_id": course_id,
                "name": name,
                "normalized": normalize_concept_name(name),
                "description": description,
                "status": status,
                "now": NOW,
            },
        )
        if status == "CONFIRMED":
            await SegmentSearchService.upsert_segment_index(session, ENTITY_CONCEPT, [concept_id])


async def seed_library_record_concept(
    app: FastAPI, *, record_id: str, concept_id: str, evidence_count: int = 1
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_concepts (id, record_id, concept_id, relevance, "
                "evidence_count, created_at, updated_at) "
                "VALUES (:id, :record_id, :concept_id, 0.8, :evidence_count, :now, :now)"
            ),
            {
                "id": f"rc-{record_id}-{concept_id}",
                "record_id": record_id,
                "concept_id": concept_id,
                "evidence_count": evidence_count,
                "now": NOW,
            },
        )


async def invoke_search_library(
    app: FastAPI, *, scope: ChatScope, course_id: str | None, query: str
) -> dict[str, Any]:
    """绑定运行期范围后直调 search_library，返回解析后的工具 JSON 载荷。"""
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            scope=scope,
            course_id=course_id,
            session_factory=app.state.session_factory,
            session_id="sess-invoke",
        )
    )
    try:
        return cast(dict[str, Any], json.loads(await search_library.ainvoke({"query": query})))
    finally:
        reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_search_library_concept_enrichment_course_scope(tmp_path: Path) -> None:
    """COURSE 会话：概念命中→概念名扩展命中分片；载荷三类（工单 04 契约）。"""
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await seed_library_course(app, "course-1", "数据库课程")
        await seed_library_concept(
            app,
            concept_id="concept-mvcc",
            course_id="course-1",
            name="MVCC",
            description="多版本并发控制机制",
        )
        await seed_library_transcript(
            app,
            record_id="record-a",
            course_id="course-1",
            title="第 3 讲",
            segment_id="seg-a",
            content="MVCC 通过 ReadView 实现事务可见性",
            start_ms=1000,
            end_ms=5000,
        )
        await seed_library_record_concept(
            app, record_id="record-a", concept_id="concept-mvcc", evidence_count=2
        )

        # 原查询「并发控制」在分片 FTS 零命中，命中只能来自概念名扩展 → 增强生效。
        payload = await invoke_search_library(
            app, scope=ChatScope.COURSE, course_id="course-1", query="并发控制"
        )
        assert payload["concept_hints"] == [
            {
                "concept_id": "concept-mvcc",
                "canonical_name": "MVCC",
                "description": "多版本并发控制机制",
                "course_id": "course-1",
            }
        ]
        assert [hit["record_id"] for hit in payload["evidence_hits"]] == ["record-a"]
        assert payload["evidence_hits"][0]["time"] == "0:01-0:05"
        assert payload["evidence_hits"][0]["quote"] == "MVCC 通过 ReadView 实现事务可见性"
        assert payload["evidence_hits"][0]["source_title"] == "第 3 讲"
        assert payload["evidence_hits"][0]["channel"] == "concept_expansion"
        assert "occurrences" not in payload


@pytest.mark.anyio
async def test_search_library_all_scope_expands_within_concept_course(tmp_path: Path) -> None:
    """ALL 会话：概念只在归属课程内扩展；原查询保持全库范围。"""
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await seed_library_course(app, "course-1", "数据库课程")
        await seed_library_course(app, "course-2", "算法课程")
        await seed_library_concept(
            app,
            concept_id="concept-mvcc",
            course_id="course-1",
            name="MVCC",
            description="多版本并发控制",
        )
        await seed_library_transcript(
            app,
            record_id="record-1",
            course_id="course-1",
            title="DB 第 3 讲",
            segment_id="seg-1",
            content="MVCC 通过 ReadView 实现事务可见性",
        )
        # 课程 2 分片含原查询词（原查询全库命中）与概念名字样（概念扩展不得混入）。
        await seed_library_transcript(
            app,
            record_id="record-2",
            course_id="course-2",
            title="算法第 1 讲",
            segment_id="seg-2",
            content="并发控制依赖与 MVCC 类似的隔离思想",
        )

        payload = await invoke_search_library(
            app, scope=ChatScope.ALL, course_id=None, query="并发控制"
        )
        hit_records = {hit["record_id"] for hit in payload["evidence_hits"]}
        assert hit_records == {"record-1", "record-2"}, "原查询全库 + 概念扩展限归属课程"
        assert [item["concept_id"] for item in payload["concept_hints"]] == ["concept-mvcc"]


@pytest.mark.anyio
async def test_search_library_excludes_candidate_concepts(tmp_path: Path) -> None:
    """候选概念不进 Agent 上下文：直插索引行的纵深防线（SQL CONFIRMED-only）。"""
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await seed_library_course(app, "course-1", "数据库课程")
        await seed_library_concept(
            app,
            concept_id="concept-cand",
            course_id="course-1",
            name="MVCC",
            description="多版本并发控制",
            status="CANDIDATE",
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO segment_search_index (body, entity_type, entity_id) "
                    "VALUES (:body, 'CONCEPT', :concept_id)"
                ),
                {
                    "body": tokenize("MVCC 多版本并发控制"),
                    "concept_id": "concept-cand",
                },
            )

        payload = await invoke_search_library(
            app, scope=ChatScope.COURSE, course_id="course-1", query="并发控制"
        )
        assert payload["concept_hints"] == [], "候选概念即使有索引行也不得命中"
        assert payload["evidence_hits"] == []


@pytest.mark.anyio
async def test_search_library_degrades_without_concepts(tmp_path: Path) -> None:
    """无 brain 课程退化：零概念时检索面为空；COURSE/ALL 不做 LIKE 兜底
    （contract §4：LIKE 只由 RECORD/LIBRARY_ITEM 的记录级路径继承）。"""
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await seed_library_course(app, "course-1", "分布式系统")
        # 粘贴记录只有转写全文、无分片：COURSE 范围 FTS 零命中 → 如实返回未找到。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO records (id, course_id, capture_type, title, status, "
                    "duration_ms, created_at, updated_at, deleted_at) "
                    "VALUES (:id, 'course-1', 'PASTE', '粘贴笔记', 'COMPLETED', 0, "
                    ":now, :now, NULL)"
                ),
                {"id": "record-paste", "now": NOW},
            )
            await session.execute(
                text(
                    "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                    "edited_by_user, created_at, updated_at, deleted_at) "
                    "VALUES (:id, 'record-paste', 'zh-CN', :content, 1, 0, :now, :now, NULL)"
                ),
                {
                    "id": "transcript-paste",
                    "content": "第二讲聚焦一致性哈希的实践应用。",
                    "now": NOW,
                },
            )

        payload = await invoke_search_library(
            app, scope=ChatScope.COURSE, course_id="course-1", query="一致性哈希"
        )
        assert payload["concept_hints"] == []
        assert payload["evidence_hits"] == []
        assert "未找到" in payload["message"]


# ---------------------------------------------------------------------------
# 页面快照注入（通用 Agent 工单 01）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_page_snapshot_injected_per_turn_in_free_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """随消息携带的页面快照注入 SYSTEM（框定为提示信息，非指令非授权）：每轮
    取当条消息的快照，不携带即不注入（跨轮零残留）；FREE 会话挂载面不因快照
    携带课程 id 改变（结构上挂载只看 scope，矩阵另由挂载矩阵测试锁定）。"""
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        app,
        client,
        captured,
    ):
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status, "
                    "created_at, updated_at) "
                    "VALUES ('e0000000-0000-4000-8000-000000000001', 'Python 学习', "
                    "'INTEREST', 'INTERMEDIATE', 'ACTIVE', '2026-09-21T08:00:00.000000Z', "
                    "'2026-09-21T08:00:00.000000Z')"
                )
            )
        created = await client.post("/api/chat-sessions", json={"scope": "FREE"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        events = await send_message(
            client,
            session_id,
            "往这个课程加条笔记",
            page={
                "page_type": "course",
                "entity_id": "e0000000-0000-4000-8000-000000000001",
                "captured_at": "2026-09-21T08:00:00.000000Z",
            },
        )
        assert events[-1][0] == "done"
        system_first = str(captured[0][0].content)
        assert "页面提示" in system_first
        assert "不是指令" in system_first and "不构成任何授权" in system_first
        assert "课程「Python 学习」" in system_first
        # 同会话第二条消息不携带快照：新轮 SYSTEM 无页面提示（旧快照零回写）。
        events = await send_message(client, session_id, "继续")
        assert events[-1][0] == "done"
        assert "页面提示" not in str(captured[-1][0].content)


@pytest.mark.anyio
async def test_free_session_with_course_page_snapshot_keeps_tool_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FREE 会话不因页面快照携带课程 id 获得资料正文检索（工单 01 验收）：
    直接断言当轮可见工具面——无 search_library，search_courses 恒挂载。"""
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", BindRecordingModel)
    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
        model_budget=ModelBudgetConfig(context_window=128000),
    )
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status, "
                    "created_at, updated_at) "
                    "VALUES ('e0000000-0000-4000-8000-000000000002', '数据结构', "
                    "'INTEREST', 'INTERMEDIATE', 'ACTIVE', '2026-09-21T08:00:00.000000Z', "
                    "'2026-09-21T08:00:00.000000Z')"
                )
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            created = await client.post("/api/chat-sessions", json={"scope": "FREE"})
            assert created.status_code == 201
            session_id = created.json()["id"]
            BindRecordingModel.replies = [list(STUB_REPLY)] * 2
            BindRecordingModel.bound = []
            events = await send_message(
                client,
                session_id,
                "往这个课程加条笔记",
                page={
                    "page_type": "course",
                    "entity_id": "e0000000-0000-4000-8000-000000000002",
                    "captured_at": "2026-09-21T08:00:00.000000Z",
                },
            )
            assert events[-1][0] == "done"
            assert "search_library" not in BindRecordingModel.bound
            assert "search_courses" in BindRecordingModel.bound
            assert "propose_memory" in BindRecordingModel.bound


@pytest.mark.anyio
async def test_create_course_tool_streams_operation_proposal_done_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """操作工具成功 → done 载荷 operation_proposals（零新 SSE 事件类型）；
    提案落库 PENDING、未确认零课程；FREE 会话恒挂载 create_course。"""
    replies: list[StubReply] = [
        ToolCallReply(
            "create_course",
            {
                "name": "现代诗赏析",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        ),
        ["已为你创建课程提案，请确认。"],
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        captured_bound,
    ):
        created = await client.post("/api/chat-sessions", json={"scope": "FREE"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        events = await send_message(client, session_id, "帮我创建一个课程")

    done = events[-1][1]
    assert events[-1][0] == "done"
    proposals = done["operation_proposals"]
    assert len(proposals) == 1
    assert proposals[0]["action"] == "create_course"
    assert proposals[0]["payload"]["name"] == "现代诗赏析"
    assert proposals[0]["payload"]["depth"] == "BEGINNER"
    assert isinstance(proposals[0]["proposal_id"], str)
    # FREE 会话恒挂载操作工具组（spec 决策 12：写工具与范围解耦）。
    bound_names = [getattr(tool, "name", "") for tool in captured_bound[-1]]
    assert "create_course" in bound_names

    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        proposal_row = await (
            await connection.execute(
                "SELECT proposal_type, status FROM agent_proposals WHERE session_id = ?",
                (session_id,),
            )
        ).fetchone()
        course_count = await (await connection.execute("SELECT count(*) FROM courses")).fetchone()
    assert proposal_row is not None
    assert tuple(proposal_row) == ("COURSE_CREATE", "PENDING")
    assert course_count is not None and course_count[0] == 0


@pytest.mark.anyio
async def test_interrupted_stream_keeps_pending_operation_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """工单 04：SSE 断开/用户停止后，已产生的待确认操作提案保留（提案写入是
    独立事务、与流生命周期解耦）、流停止后不再新增提案；保留的提案仍可经
    确认端点执行（用户故事 13：停止生成后待确认操作仍保留等我决定）。"""
    replies: list[StubReply] = [
        ToolCallReply(
            "create_course",
            {"name": "中断课", "learning_context": "INTEREST", "depth": "BEGINNER"},
        ),
        ["已创建提案。"],
    ]
    release = asyncio.Event()
    replies[1] = GatedReply(prefix=(), release=release)
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured,
    ):
        created = await client.post("/api/chat-sessions", json={"scope": "FREE"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        turn_id = await submit_turn(client, session_id, "帮我创建一个课程")
        # 工具调用已返回待确认提案（轮次事件推进到 tool_result 后停住）；
        # 取消后过程留痕，确认卡继续独立可用。
        for _ in range(150):
            snapshot = cast(
                dict[str, Any],
                (await client.get(f"/api/chat-turns/{turn_id}")).json(),
            )
            if snapshot["status"] == "RUNNING" and snapshot["last_seq"] >= 2:
                break
            if snapshot["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
                pytest.fail(f"轮次提前终态: {snapshot['status']}")
            await asyncio.sleep(0.1)
        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        await wait_turn_terminal(client, turn_id)
        release.set()

        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            proposal_row = await (
                await connection.execute(
                    "SELECT id, status FROM agent_proposals WHERE session_id = ?",
                    (session_id,),
                )
            ).fetchone()
            counts_row = await (
                await connection.execute(
                    "SELECT (SELECT count(*) FROM agent_proposals), (SELECT count(*) FROM courses)"
                )
            ).fetchone()
        assert proposal_row is not None
        assert counts_row is not None
        proposal_id, status = str(proposal_row[0]), str(proposal_row[1])
        proposal_count, course_count = int(counts_row[0]), int(counts_row[1])
        assert status == "PENDING"
        # 流已停止：提案恒一条（Agent 不再产生新操作）、确认前零课程。
        assert proposal_count == 1
        assert course_count == 0
        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        process = next(item for item in history if item["role"] == "USER")["response_processes"][0]
        assert process["status"] == "INTERRUPTED"
        assert process["entries"][0]["status"] == "AWAITING_CONFIRMATION"
        assert process["entries"][0]["hits"] is None
        rows = await message_rows(tmp_path, session_id)
        assert all(role != "ASSISTANT" for role, _content in rows)
        # 保留的待确认提案仍可决定：确认 → APPLIED + 回执课程。
        confirmed = await client.post(f"/api/proposals/{proposal_id}/confirm")
        assert confirmed.status_code == 200
        body = confirmed.json()
        assert body["status"] == "APPLIED"
        assert isinstance(body["result"]["course_id"], str)
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            final_courses = await (
                await connection.execute("SELECT count(*) FROM courses")
            ).fetchone()
        assert final_courses is not None and final_courses[0] == 1


@pytest.mark.anyio
async def test_new_user_message_discards_pending_plan_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec 用户故事 11「确认卡关闭即弃」：新用户消息 = 话题翻篇，本会话
    PENDING 计划草案提案批量置 REJECTED（learning_plans 零写入不变）；其余
    操作提案与其他会话的草案不受影响；补答（复用原 user 行）不是翻篇。"""
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 3) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)

        async def seed_proposal(proposal_id: str, proposal_type: str, chat_session_id: str) -> None:
            async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
                await connection.execute(
                    "INSERT INTO agent_proposals"
                    " (id, proposal_type, status, session_id, payload_json, created_at)"
                    " VALUES (?, ?, 'PENDING', ?, '{}',"
                    " strftime('%Y-%m-%dT%H:%M:%S', 'now'))",
                    (proposal_id, proposal_type, chat_session_id),
                )
                await connection.commit()

        async def status_of(proposal_id: str) -> str | None:
            async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
                row = await (
                    await connection.execute(
                        "SELECT status FROM agent_proposals WHERE id = ?",
                        (proposal_id,),
                    )
                ).fetchone()
            return None if row is None else str(row[0])

        await seed_proposal("draft-1", "OP_PLAN_CONFIRM", session_id)
        await seed_proposal("other-1", "OP_COURSE_ARCHIVE", session_id)
        await seed_proposal("draft-other-session", "OP_PLAN_CONFIRM", "sess-other")

        # 新消息（话题翻篇）：本会话草案弃置，其余操作提案与其他会话草案保留。
        events = await send_message(client, session_id, "换个话题聊点别的")
        assert events[-1][0] == "done"
        assert await status_of("draft-1") == "REJECTED"
        assert await status_of("other-1") == "PENDING"
        assert await status_of("draft-other-session") == "PENDING"

        # 弃置不产生半成品计划数据：计划业务表零写入。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            plans = await (
                await connection.execute("SELECT count(*) FROM learning_plans")
            ).fetchone()
        assert plans is not None and plans[0] == 0

        # 补答（轮次被停止后重发同一内容，复用原 user 行）不是翻篇：停止后
        # 落库的 USER 行之后 seed 新草案，重发不触发弃置。
        stopped_turn = await submit_turn(client, session_id, "会被中断的问题")
        cancelled = await client.post(f"/api/chat-turns/{stopped_turn}/cancel")
        assert cancelled.status_code == 200
        await wait_turn_terminal(client, stopped_turn)
        await seed_proposal("draft-2", "OP_PLAN_CONFIRM", session_id)
        await submit_turn(client, session_id, "会被中断的问题")
        assert await status_of("draft-2") == "PENDING"


@pytest.mark.anyio
async def test_interrupted_stream_keeps_direct_execution_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """工单 07：SSE 断开不改变已提交的直执行事实——operation 行与业务写同事务，
    断流后经持久化查询（回执卡恢复链数据源）恢复一致；直执行恰一次（无第二条
    行、零提案）。对照上例（提案版中断）：提案保留待决，本例操作已发生且可查。"""
    from app.modules.agent.runs.schemas import AuthMode

    release = asyncio.Event()
    replies: list[StubReply] = [
        ToolCallReply(
            "create_course",
            {"name": "直执行断流课", "learning_context": "INTEREST", "depth": "BEGINNER"},
        ),
        GatedReply(prefix=(), release=release),
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured,
    ):
        created = await client.post("/api/chat-sessions", json={"scope": "FREE"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        turn_id = await submit_turn(
            client, session_id, "帮我创建一个课程", auth_mode=AuthMode.AUTO_APPROVE
        )
        # 直执行已完成（operation 与课程同事务提交、事件推进到 tool_result）
        # 后发出持久取消：已提交事实不回滚，取消只收口轮次。
        for _ in range(150):
            snapshot = cast(
                dict[str, Any],
                (await client.get(f"/api/chat-turns/{turn_id}")).json(),
            )
            if snapshot["status"] == "RUNNING" and snapshot["last_seq"] >= 2:
                break
            if snapshot["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
                pytest.fail(f"轮次提前终态: {snapshot['status']}")
            await asyncio.sleep(0.1)
        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        await wait_turn_terminal(client, turn_id)
        release.set()

        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            operation_rows = await (
                await connection.execute(
                    "SELECT action, status, proposal_id, run_id FROM agent_operations"
                )
            ).fetchall()
            counts_row = await (
                await connection.execute(
                    "SELECT (SELECT count(*) FROM courses), (SELECT count(*) FROM agent_proposals)"
                )
            ).fetchone()
        assert counts_row is not None
        # 直执行恰一次：一门课程、一条 SUCCEEDED 单步行、零提案。
        assert tuple(counts_row) == (1, 0)
        assert [tuple(row) for row in operation_rows] == [
            ("create_course", "SUCCEEDED", None, None)
        ]
        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        process = next(item for item in history if item["role"] == "USER")["response_processes"][0]
        assert process["status"] == "INTERRUPTED"
        assert process["entries"][0]["status"] == "SUCCEEDED"
        rows = await message_rows(tmp_path, session_id)
        assert all(role != "ASSISTANT" for role, _content in rows)

        # 断线后经持久化查询恢复一致（不依赖 SSE 仍在连接）：会话过滤命中该行，
        # 授权依据携带档位——回执卡恢复链数据源口径。
        recovered = await client.get("/api/agent/operations", params={"session_id": session_id})
        assert recovered.status_code == 200
        items = recovered.json()
        assert len(items) == 1
        assert items[0]["action"] == "create_course"
        assert items[0]["status"] == "SUCCEEDED"
        assert items[0]["authorization"]["auth_mode"] == "AUTO_APPROVE"


@pytest.mark.anyio
async def test_response_process_separates_commentary_and_all_parallel_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[StubReply] = [
        ToolCallReply(
            "search_courses",
            {"query": "Redis"},
            call_id="courses-a",
            commentary="我先查询课程，再核对当前时间。",
            parallel_calls=(
                ToolCallReply("search_courses", {"query": "Python"}, call_id="courses-b"),
                ToolCallReply("get_current_time", {}, call_id="time-c"),
            ),
        ),
        ["最终课程回答。"],
        list(STUB_REPLY),
    ]
    async with streaming_chat_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        captured,
    ):
        session_id = await create_session(client)
        events = await send_message(client, session_id, "讲解课程")
        assert events[-1][0] == "done"
        assert events[-1][1]["content"] == "最终课程回答。"
        process = events[-1][1]["process"]
        assert process["status"] == "COMPLETED"
        assert process["history_saved"] is True
        assert process["entries"][0]["text"] == "我先查询课程，再核对当前时间。"
        tools = [entry for entry in process["entries"] if entry["kind"] == "tool"]
        assert [entry["id"] for entry in tools] == ["courses-a", "courses-b", "time-c"]
        assert all(entry["status"] == "SUCCEEDED" for entry in tools)
        assert tools[2]["hits"] is None
        assert tools[2]["query"] == ""
        calls = [payload["tool_call_id"] for name, payload in events if name == "tool_call"]
        assert calls == ["courses-a", "courses-b", "time-c"]
        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        user = next(message for message in history if message["role"] == "USER")
        assert user["response_processes"] == [process]
        assert history[-1]["content"] == "最终课程回答。"
        await send_message(client, session_id, "继续")
        assert all(
            "我先查询课程" not in str(message.content)
            for message in captured[-1]
            if not isinstance(message, AIMessage) or not message.tool_calls
        )


@pytest.mark.anyio
async def test_response_process_correlates_out_of_order_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent import message_service
    from app.modules.agent.graph import (
        ChatStreamEvent,
        ChatTokenEvent,
        ChatToolCallEvent,
        ChatToolResultEvent,
    )

    async def events(**_kwargs: object) -> AsyncGenerator[ChatStreamEvent, None]:
        yield ChatToolCallEvent("search_courses", "first", "call-a", "model-1")
        yield ChatToolCallEvent("search_courses", "second", "call-b", "model-1")
        yield ChatToolResultEvent("search_courses", 2, True, "call-b")
        yield ChatToolResultEvent("search_courses", 0, False, "call-a")
        yield ChatTokenEvent("可用的最终回答", "model-2")

    monkeypatch.setattr(message_service, "stream_chat_reply", events)
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        streamed = await send_message(client, session_id, "查询")
        process = streamed[-1][1]["process"]
        tools = process["entries"]
        assert [(entry["id"], entry["status"], entry["hits"]) for entry in tools] == [
            ("call-a", "FAILED", 0),
            ("call-b", "SUCCEEDED", 2),
        ]
        assert process["status"] == "COMPLETED"
