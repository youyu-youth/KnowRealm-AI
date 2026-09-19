"""CB-01 检索基线评测（合成语料口径）：FTS BM25 + Concept 扩展召回四维。

评测脚本可重复执行（pytest 内嵌，临时库随 tmp_path 清理）：

    uv run pytest tests/test_course_brain_retrieval_eval.py

合成语料（CONCEPTS / SEGMENTS / RECORD_CONCEPTS，Course = 数据库与网络）覆盖
CB-01 四类样例：同义词（可见性 → MVCC）、简称/展开（TCP → 传输控制协议）、
跨记录统计（MVCC 去重记录数）、原文定位（逐字 quote 回表 + 时间/页码）。
口径与结论记录：docs/evaluation/course-brain-retrieval-baseline.md。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, TypedDict

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.course_brain.schemas import CourseBrainSearchOut
from app.modules.course_brain.service import CourseBrainService, normalize_concept_name
from app.modules.search.segment_service import (
    ENTITY_CONCEPT,
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-15T08:00:00.000000Z"

COURSE_ID = "e0000000-0000-4000-8000-000000000001"
RECORD_DB_1 = "e0000000-0000-4000-8000-000000000002"
RECORD_DB_2 = "e0000000-0000-4000-8000-000000000003"
RECORD_NET = "e0000000-0000-4000-8000-000000000004"

CONCEPT_MVCC = "e0000000-0000-4000-8000-000000000101"
CONCEPT_TCP = "e0000000-0000-4000-8000-000000000102"


class ConceptFixture(TypedDict):
    id: str
    name: str
    description: str


class AudioSegmentFixture(TypedDict):
    id: str
    record_id: str
    kind: Literal["audio"]
    sequence_no: int
    content: str
    start_ms: int
    end_ms: int


class DocumentSegmentFixture(TypedDict):
    id: str
    record_id: str
    kind: Literal["document"]
    sequence_no: int
    content: str
    page_no: int


SegmentFixture = AudioSegmentFixture | DocumentSegmentFixture


class RecordConceptFixture(TypedDict):
    id: str
    record_id: str
    concept_id: str
    evidence_count: int


# 合成语料：概念（CONFIRMED，应用层直接写入模拟已构建图谱）。
CONCEPTS: list[ConceptFixture] = [
    {
        "id": CONCEPT_MVCC,
        "name": "MVCC",
        "description": "多版本并发控制；通过快照读与 ReadView 判定事务可见性",
    },
    {
        "id": CONCEPT_TCP,
        "name": "传输控制协议",
        "description": "面向连接的可靠传输协议（TCP）",
    },
]

# 合成语料：分片（音频转写 / 文档），逐字 quote 回表的对照源。
SEGMENTS: list[SegmentFixture] = [
    {
        "id": "es-1",
        "record_id": RECORD_DB_1,
        "kind": "audio",
        "sequence_no": 0,
        "content": "MVCC 通过 ReadView 实现事务可见性，读取的是快照数据。",
        "start_ms": 10000,
        "end_ms": 25000,
    },
    {
        "id": "es-2",
        "record_id": RECORD_DB_1,
        "kind": "audio",
        "sequence_no": 1,
        "content": "当版本链可见性判断失败时，事务会沿着 undo log 找到旧版本。",
        "start_ms": 25000,
        "end_ms": 40000,
    },
    {
        "id": "es-3",
        "record_id": RECORD_DB_2,
        "kind": "audio",
        "sequence_no": 0,
        "content": "MVCC 的并发控制依赖快照读，避免读写冲突。",
        "start_ms": 5000,
        "end_ms": 18000,
    },
    {
        "id": "es-4",
        "record_id": RECORD_NET,
        "kind": "document",
        "sequence_no": 0,
        "content": "传输控制协议提供面向连接的可靠字节流服务。",
        "page_no": 12,
    },
    {
        "id": "es-5",
        "record_id": RECORD_NET,
        "kind": "document",
        "sequence_no": 1,
        "content": "TCP 使用三次握手建立连接。",
        "page_no": 13,
    },
]

SEGMENT_BY_ID = {segment["id"]: segment for segment in SEGMENTS}

# 合成语料：Concept ↔ Record 出现关系（跨记录统计的派生源）。
RECORD_CONCEPTS: list[RecordConceptFixture] = [
    {"id": "erc-1", "record_id": RECORD_DB_1, "concept_id": CONCEPT_MVCC, "evidence_count": 2},
    {"id": "erc-2", "record_id": RECORD_DB_2, "concept_id": CONCEPT_MVCC, "evidence_count": 1},
    {"id": "erc-3", "record_id": RECORD_NET, "concept_id": CONCEPT_TCP, "evidence_count": 2},
]


@asynccontextmanager
async def running_eval_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def seed_corpus(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, status, "
                "created_at, updated_at) "
                "VALUES (:id, '数据库与网络', 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)"
            ),
            {"id": COURSE_ID, "now": NOW},
        )
        for record_id, title, capture_type in (
            (RECORD_DB_1, "数据库原理 第3讲", "RECORDING"),
            (RECORD_DB_2, "数据库原理 第5讲", "RECORDING"),
            (RECORD_NET, "计算机网络讲义", "DOCUMENT_IMPORT"),
        ):
            await session.execute(
                text(
                    "INSERT INTO records (id, course_id, capture_type, title, status, "
                    "duration_ms, created_at, updated_at) "
                    "VALUES (:id, :course_id, :capture_type, :title, 'COMPLETED', 60000, "
                    ":now, :now)"
                ),
                {
                    "id": record_id,
                    "course_id": COURSE_ID,
                    "capture_type": capture_type,
                    "title": title,
                    "now": NOW,
                },
            )
        # 音频分片宿主：每记录一个 file + transcript（零时间戳退化的反面：本语料带时间轴）。
        for index, record_id in enumerate((RECORD_DB_1, RECORD_DB_2)):
            file_id = f"efile-{index}"
            transcript_id = f"etranscript-{index}"
            await session.execute(
                text(
                    "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                    "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                    "created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', "
                    "'audio/ogg', 1, 60000, 0, 'h', :now, :now, NULL)"
                ),
                {"id": file_id, "record_id": record_id, "now": NOW},
            )
            await session.execute(
                text(
                    "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                    "edited_by_user, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'zh-CN', '语料占位', 1, 0, :now, :now, NULL)"
                ),
                {"id": transcript_id, "record_id": record_id, "now": NOW},
            )
            for segment in SEGMENTS:
                if segment["kind"] != "audio" or segment["record_id"] != record_id:
                    continue
                await session.execute(
                    text(
                        "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                        "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                        "speaker, content, content_hash) "
                        "VALUES (:id, :transcript_id, :record_id, :file_id, :sequence_no, "
                        ":start_ms, :end_ms, :start_ms, :end_ms, NULL, :content, :content_hash)"
                    ),
                    {
                        "id": segment["id"],
                        "transcript_id": transcript_id,
                        "record_id": record_id,
                        "file_id": file_id,
                        "sequence_no": segment["sequence_no"],
                        "start_ms": segment["start_ms"],
                        "end_ms": segment["end_ms"],
                        "content": segment["content"],
                        "content_hash": content_hash(segment["content"]),
                    },
                )
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                "created_at, updated_at, deleted_at) "
                "VALUES ('efile-doc', :record_id, 'DOCUMENT', 'UPLOADED', 'd.pdf', 'd.pdf', "
                "'application/pdf', 1, 0, 0, 'h', :now, :now, NULL)"
            ),
            {"record_id": RECORD_NET, "now": NOW},
        )
        for segment in SEGMENTS:
            if segment["kind"] != "document":
                continue
            await session.execute(
                text(
                    "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                    "library_item_id, sequence_no, page_no, section_title, content, "
                    "start_offset, end_offset, content_hash) "
                    "VALUES (:id, :course_id, :record_id, 'efile-doc', NULL, :sequence_no, "
                    ":page_no, NULL, :content, 0, 0, :content_hash)"
                ),
                {
                    "id": segment["id"],
                    "course_id": COURSE_ID,
                    "record_id": segment["record_id"],
                    "sequence_no": segment["sequence_no"],
                    "page_no": segment["page_no"],
                    "content": segment["content"],
                    "content_hash": content_hash(segment["content"]),
                },
            )
        for concept in CONCEPTS:
            await session.execute(
                text(
                    "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                    "description, concept_type, importance, status, source, created_at, "
                    "updated_at) "
                    "VALUES (:id, :course_id, :name, :normalized, :description, 'TERM', 3, "
                    "'CONFIRMED', 'AI_EXTRACTED', :now, :now)"
                ),
                {
                    "id": concept["id"],
                    "course_id": COURSE_ID,
                    "name": concept["name"],
                    "normalized": normalize_concept_name(concept["name"]),
                    "description": concept["description"],
                    "now": NOW,
                },
            )
        for record_concept in RECORD_CONCEPTS:
            await session.execute(
                text(
                    "INSERT INTO record_concepts (id, record_id, concept_id, knowledge_point_id, "
                    "relevance, evidence_count, first_start_ms, created_at, updated_at) "
                    "VALUES (:id, :record_id, :concept_id, NULL, 0.8, :evidence_count, 0, "
                    ":now, :now)"
                ),
                {**record_concept, "now": NOW},
            )
        await SegmentSearchService.upsert_segment_index(
            session,
            ENTITY_TRANSCRIPT_SEGMENT,
            [segment["id"] for segment in SEGMENTS if segment["kind"] == "audio"],
        )
        await SegmentSearchService.upsert_segment_index(
            session,
            ENTITY_DOCUMENT_SEGMENT,
            [segment["id"] for segment in SEGMENTS if segment["kind"] == "document"],
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_CONCEPT, [concept["id"] for concept in CONCEPTS]
        )


async def run_search(app: FastAPI, query: str, limit: int = 8) -> CourseBrainSearchOut:
    async with app.state.session_factory() as session:
        return await CourseBrainService.search(session, COURSE_ID, query, limit)


async def baseline_segment_hits(app: FastAPI, query: str) -> set[str]:
    """对照基线：原查询单跑 Segment FTS（无 Concept 扩展）的命中分片 id。"""
    async with app.state.session_factory() as session:
        hits = await SegmentSearchService.search_scope_segments(session, COURSE_ID, query, 8)
    return {hit.segment_id for hit in hits}


@pytest.mark.anyio
async def test_eval_dimension_concept_hit_top_k(tmp_path: Path) -> None:
    """维度一：四类查询的 Concept FTS top-4 均必须命中目标概念。"""
    async with running_eval_app(tmp_path / "KnowRealm") as (app, _client):
        await seed_corpus(app)
        expectations = [
            ("可见性", CONCEPT_MVCC),
            ("MVCC", CONCEPT_MVCC),
            ("TCP", CONCEPT_TCP),
            ("传输控制协议", CONCEPT_TCP),
        ]
        for query, expected_concept_id in expectations:
            result = await run_search(app, query)
            matched_ids = [concept.concept_id for concept in result.matched_concepts]
            assert expected_concept_id in matched_ids, f"概念命中失败：{query}"


@pytest.mark.anyio
async def test_eval_dimension_expansion_gain_over_bm25(tmp_path: Path) -> None:
    """维度二：canonical_name 并跑相对原查询 BM25 有可量化增益（两类样例各 +1 分片）。"""
    async with running_eval_app(tmp_path / "KnowRealm") as (app, _client):
        await seed_corpus(app)
        cases = [
            # 同义词样例：原查询命中 R1 两条，MVCC 扩展补回 R2 的 es-3。
            # 注：扩展项为命中概念的 canonical_name；查询 "可见性" 匹配 MVCC 的
            # description，故扩展词是 "MVCC"（description 仅用于概念命中，不参与扩展）。
            ("可见性", {"es-1", "es-2"}, {"es-3"}),
            # 简称/展开样例：原查询只命中含 "TCP" 的 es-5，展开词补回全称分片 es-4。
            ("TCP", {"es-5"}, {"es-4"}),
        ]
        for query, baseline_expected, gained_expected in cases:
            baseline = await baseline_segment_hits(app, query)
            expanded = await run_search(app, query)
            expanded_ids = {hit.segment_id for hit in expanded.occurrences}
            assert baseline == baseline_expected, f"基线召回不符合预期：{query}"
            assert expanded_ids - baseline == gained_expected, f"扩展增益不符合预期：{query}"
            assert len(expanded_ids) > len(baseline), f"扩展未产生增益：{query}"


@pytest.mark.anyio
async def test_eval_dimension_occurrence_record_dedup(tmp_path: Path) -> None:
    """维度三：occurrences 逐条保留分片命中，跨记录计数按 record 去重且与派生统计一致。"""
    async with running_eval_app(tmp_path / "KnowRealm") as (app, _client):
        await seed_corpus(app)
        result = await run_search(app, "MVCC")
        assert len(result.occurrences) == 2
        assert {hit.record_id for hit in result.occurrences} == {RECORD_DB_1, RECORD_DB_2}
        matcher = result.matched_concepts[0]
        assert matcher.concept_id == CONCEPT_MVCC
        assert matcher.record_count == 2
        assert matcher.occurrence_count == 3

        synonym = await run_search(app, "可见性")
        assert len(synonym.occurrences) == 3
        assert {hit.record_id for hit in synonym.occurrences} == {RECORD_DB_1, RECORD_DB_2}


@pytest.mark.anyio
async def test_eval_dimension_quote_verbatim_lookup(tmp_path: Path) -> None:
    """维度四：全部命中 quote 与合成语料逐字一致，音频带时间轴、文档带页码。"""
    async with running_eval_app(tmp_path / "KnowRealm") as (app, _client):
        await seed_corpus(app)
        total = 0
        for query in ("可见性", "MVCC", "TCP", "传输控制协议"):
            result = await run_search(app, query)
            assert result.occurrences, f"无命中：{query}"
            for hit in result.occurrences:
                segment = SEGMENT_BY_ID[hit.segment_id]
                assert hit.quote == segment["content"], f"quote 非逐字回表：{query}"
                assert hit.record_title
                if segment["kind"] == "audio":
                    assert hit.start_ms == segment["start_ms"]
                    assert hit.end_ms == segment["end_ms"]
                    assert hit.page_no is None
                else:
                    assert hit.page_no == segment["page_no"]
                    assert hit.start_ms is None
                total += 1
        assert total >= 8
