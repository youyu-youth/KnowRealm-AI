"""工单 04：LibraryRetrievalService 五档隔离、预算与 LIBRARY_ITEM 会话的失败即红用例。

覆盖 spec「硬门禁零容忍」项：scope 泄漏（LIBRARY_ITEM/RECORD/COURSE/ALL 四档
隔离）、归档/软删来源不以资料身份召回、工具预算超限截断、library 引用条目
逐字校验。数据经直插 SQL 种子（对齐 test_library_retrieval_eval 惯例），
SSE 工具事件呈现已在 test_chat_streaming 覆盖（同一装配路径）。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.agent.citations import (
    LibraryItemMaterial,
    LibraryRecordMaterial,
    parse_library_citation_reply,
)
from app.modules.agent.schemas import ChatScope
from app.modules.agent.tools.search_library import (
    MAX_TOOL_CALLS_PER_TURN,
    TOOL_RESULT_MAX_CHARS,
    TOOL_ROUND_OUTPUT_MAX_CHARS,
    LibrarySearchContext,
    ToolCallBudget,
    bind_library_context,
    reset_library_context,
    search_library,
)
from app.modules.library.retrieval import (
    LibraryRetrievalService,
    RetrievalResult,
    RetrievalScope,
)
from app.modules.search.segment_service import (
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.settings.config import save_llm_provider
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-19T08:00:00.000000Z"

COURSE_ML = "b0000000-0000-4000-8000-000000000001"
COURSE_DB = "b0000000-0000-4000-8000-000000000002"

REC_ML_AUDIO = "b0000000-0000-4000-8000-000000000011"
REC_ML_PASTE = "b0000000-0000-4000-8000-000000000012"
REC_DB_DOC = "b0000000-0000-4000-8000-000000000013"
REC_GLOBAL_PASTE = "b0000000-0000-4000-8000-000000000014"
REC_ML_DELETED = "b0000000-0000-4000-8000-000000000015"

ITEM_ML_AUDIO = "b0000000-0000-4000-8000-000000000021"
ITEM_ML_TEXT = "b0000000-0000-4000-8000-000000000022"
ITEM_WEB = "b0000000-0000-4000-8000-000000000023"
ITEM_WEB_ARCHIVED = "b0000000-0000-4000-8000-000000000024"
ITEM_WEB_DELETED = "b0000000-0000-4000-8000-000000000025"


@asynccontextmanager
async def retrieval_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def _insert_library_item(
    app: FastAPI,
    item_id: str,
    *,
    source_type: str,
    title: str,
    course_id: str | None,
    status: str = "ACTIVE",
    deleted: bool = False,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO library_items (id, course_id, source_type, title, "
                "content_hash, metadata_json, status, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, :source_type, :title, :hash, '{}', :status, "
                ":now, :now, :deleted_at)"
            ),
            {
                "id": item_id,
                "course_id": course_id,
                "source_type": source_type,
                "title": title,
                "hash": f"hash-{item_id}",
                "status": status,
                "now": NOW,
                "deleted_at": "2026-09-18T00:00:00.000000Z" if deleted else None,
            },
        )


async def _link_item_record(app: FastAPI, item_id: str, record_id: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO library_item_records (library_item_id, record_id, role, "
                "sequence_no, created_at) VALUES (:item_id, :record_id, 'PRIMARY', 0, :now)"
            ),
            {"item_id": item_id, "record_id": record_id, "now": NOW},
        )


async def _insert_record(
    app: FastAPI,
    record_id: str,
    *,
    course_id: str | None,
    capture_type: str,
    title: str,
    deleted: bool = False,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, "
                "duration_ms, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, :capture_type, :title, 'COMPLETED', 60000, "
                ":now, :now, :deleted_at)"
            ),
            {
                "id": record_id,
                "course_id": course_id,
                "capture_type": capture_type,
                "title": title,
                "now": NOW,
                "deleted_at": "2026-09-18T00:00:00.000000Z" if deleted else None,
            },
        )


async def _insert_transcript_record(
    app: FastAPI,
    record_id: str,
    *,
    content: str,
    segment_id: str | None = None,
    start_ms: int = 10_000,
    end_ms: int = 25_000,
) -> None:
    """带转写的记录；segment_id 非空时同时建转写分片并同步索引。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, "
                "file_path, original_name, mime_type, file_size, duration_ms, "
                "sequence_no, content_hash, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', "
                "'audio/ogg', 1, 60000, 0, 'h', :now, :now, NULL)"
            ),
            {"id": f"file-{record_id}", "record_id": record_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, "
                "source_version, edited_by_user, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)"
            ),
            {
                "id": f"transcript-{record_id}",
                "record_id": record_id,
                "content": content,
                "now": NOW,
            },
        )
        if segment_id is not None:
            await session.execute(
                text(
                    "INSERT INTO transcript_segments (id, transcript_id, record_id, "
                    "file_id, sequence_no, record_start_ms, record_end_ms, "
                    "file_start_ms, file_end_ms, speaker, content, content_hash) "
                    "VALUES (:id, :transcript_id, :record_id, :file_id, 0, "
                    ":start_ms, :end_ms, :start_ms, :end_ms, NULL, :content, :chash)"
                ),
                {
                    "id": segment_id,
                    "transcript_id": f"transcript-{record_id}",
                    "record_id": record_id,
                    "file_id": f"file-{record_id}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "content": content,
                    "chash": content_hash(content),
                },
            )
            await SegmentSearchService.upsert_segment_index(
                session, ENTITY_TRANSCRIPT_SEGMENT, [segment_id]
            )


async def _insert_item_direct_segments(app: FastAPI, item_id: str, contents: list[str]) -> None:
    """资料直挂文档分片（03 网页剪藏形态）：library_item_id 挂靠、record_id 空。"""
    segment_ids = [f"{item_id}-seg-{index}" for index in range(len(contents))]
    async with app.state.session_factory() as session, session.begin():
        for sequence_no, (segment_id, content) in enumerate(
            zip(segment_ids, contents, strict=True)
        ):
            await session.execute(
                text(
                    "INSERT INTO document_segments (id, course_id, record_id, "
                    "record_file_id, library_item_id, sequence_no, page_no, "
                    "section_title, content, start_offset, end_offset, content_hash) "
                    "VALUES (:id, NULL, NULL, NULL, :item_id, :sequence_no, NULL, "
                    "NULL, :content, 0, 0, :chash)"
                ),
                {
                    "id": segment_id,
                    "item_id": item_id,
                    "sequence_no": sequence_no,
                    "content": content,
                    "chash": content_hash(content),
                },
            )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, segment_ids
        )


async def seed_scope_corpus(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        for course_id, name in ((COURSE_ML, "机器学习导论"), (COURSE_DB, "数据库系统")):
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)"
                ),
                {"id": course_id, "name": name, "now": NOW},
            )
    # ML 音频记录（带分片）+ 其资料条目；ML 粘贴记录（无分片）+ 其资料条目。
    await _insert_record(
        app, REC_ML_AUDIO, course_id=COURSE_ML, capture_type="RECORDING", title="梯度下降第 1 讲"
    )
    await _insert_transcript_record(
        app,
        REC_ML_AUDIO,
        content="反向传播算法利用链式法则，把损失函数对每个参数的梯度逐层传回去。",
        segment_id="ml-audio-s1",
    )
    await _insert_library_item(
        app, ITEM_ML_AUDIO, source_type="AUDIO", title="梯度下降第 1 讲", course_id=COURSE_ML
    )
    await _link_item_record(app, ITEM_ML_AUDIO, REC_ML_AUDIO)
    await _insert_record(
        app, REC_ML_PASTE, course_id=COURSE_ML, capture_type="PASTE", title="费曼学习法笔记"
    )
    await _insert_transcript_record(
        app, REC_ML_PASTE, content="费曼学习法的核心是用最简单的语言把概念讲给外行听。"
    )
    await _insert_library_item(
        app, ITEM_ML_TEXT, source_type="TEXT", title="费曼学习法笔记", course_id=COURSE_ML
    )
    await _link_item_record(app, ITEM_ML_TEXT, REC_ML_PASTE)
    # DB 文档记录（分片挂 record_file）；未归类粘贴记录（无分片，ALL 不可检索）。
    await _insert_record(
        app, REC_DB_DOC, course_id=COURSE_DB, capture_type="DOCUMENT_IMPORT", title="B+ 树讲义"
    )
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, "
                "file_path, original_name, mime_type, file_size, duration_ms, "
                "sequence_no, content_hash, created_at, updated_at, deleted_at) "
                "VALUES ('file-db-doc', :record_id, 'DOCUMENT', 'UPLOADED', 'd.pdf', "
                "'d.pdf', 'application/pdf', 1, 0, 0, 'h', :now, :now, NULL)"
            ),
            {"record_id": REC_DB_DOC, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                "library_item_id, sequence_no, page_no, section_title, content, "
                "start_offset, end_offset, content_hash) "
                "VALUES ('db-doc-s1', :course_id, :record_id, 'file-db-doc', NULL, 0, 3, "
                "NULL, :content, 0, 0, :chash)"
            ),
            {
                "course_id": COURSE_DB,
                "record_id": REC_DB_DOC,
                "content": "数据库索引最常见的结构是 B+ 树，把磁盘 IO 控制在树高以内。",
                "chash": content_hash("数据库索引最常见的结构是 B+ 树，把磁盘 IO 控制在树高以内。"),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, ["db-doc-s1"]
        )
    await _insert_record(
        app,
        REC_GLOBAL_PASTE,
        course_id=None,
        capture_type="PASTE",
        title="未归类粘贴",
    )
    await _insert_transcript_record(
        app, REC_GLOBAL_PASTE, content="全局未归类的粘贴正文，仅 ALL 可见。"
    )
    # 资料直挂分片：ACTIVE 网页剪藏可检索；ARCHIVED / 软删不以资料身份召回。
    await _insert_library_item(
        app, ITEM_WEB, source_type="WEB", title="网页剪藏正文", course_id=None
    )
    await _insert_item_direct_segments(app, ITEM_WEB, ["网页剪藏正文记录了向量检索的取舍。"])
    await _insert_library_item(
        app,
        ITEM_WEB_ARCHIVED,
        source_type="WEB",
        title="归档网页资料",
        course_id=None,
        status="ARCHIVED",
    )
    await _insert_item_direct_segments(app, ITEM_WEB_ARCHIVED, ["归档资料正文不得进入来源召回。"])
    await _insert_library_item(
        app, ITEM_WEB_DELETED, source_type="WEB", title="已删网页资料", course_id=None, deleted=True
    )
    await _insert_item_direct_segments(app, ITEM_WEB_DELETED, ["已删除资料正文不得进入来源召回。"])
    # ML 软删记录：索引行存在（转写 + 文档分片各一），任何范围不得命中——
    # 文档路径是 LEFT JOIN 记录表的泄漏面，须有独立防线用例。
    await _insert_record(
        app,
        REC_ML_DELETED,
        course_id=COURSE_ML,
        capture_type="RECORDING",
        title="已删除的第 3 讲",
        deleted=True,
    )
    await _insert_transcript_record(
        app,
        REC_ML_DELETED,
        content="支持向量机通过寻找最大间隔超平面完成分类。",
        segment_id="ml-del-s1",
    )
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, "
                "file_path, original_name, mime_type, file_size, duration_ms, "
                "sequence_no, content_hash, created_at, updated_at, deleted_at) "
                "VALUES ('file-ml-del-doc', :record_id, 'DOCUMENT', 'UPLOADED', "
                "'d.pdf', 'd.pdf', 'application/pdf', 1, 0, 1, 'h', :now, :now, NULL)"
            ),
            {"record_id": REC_ML_DELETED, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                "library_item_id, sequence_no, page_no, section_title, content, "
                "start_offset, end_offset, content_hash) "
                "VALUES ('ml-del-doc-s1', :course_id, :record_id, 'file-ml-del-doc', "
                "NULL, 0, 7, NULL, :content, 0, 0, :chash)"
            ),
            {
                "course_id": COURSE_ML,
                "record_id": REC_ML_DELETED,
                "content": "核技巧把线性不可分问题映射到高维空间完成分类。",
                "chash": content_hash("核技巧把线性不可分问题映射到高维空间完成分类。"),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, ["ml-del-doc-s1"]
        )
        # 软删记录同时挂到 ACTIVE 条目（多来源形态）：LIBRARY_ITEM 关联边界防线用例。
        await session.execute(
            text(
                "INSERT INTO library_item_records (library_item_id, record_id, role, "
                "sequence_no, created_at) "
                "VALUES (:item_id, :record_id, 'SUPPLEMENTAL', 1, :now)"
            ),
            {"item_id": ITEM_WEB, "record_id": REC_ML_DELETED, "now": NOW},
        )


async def search(app: FastAPI, scope: RetrievalScope, query: str) -> RetrievalResult:
    async with app.state.session_factory() as session:
        return await LibraryRetrievalService.search(session, scope, query)


def hit_quotas(result: RetrievalResult) -> tuple[set[str], set[str], int]:
    """命中摘要：(record_id 集, 直挂条目 id 集, 命中数)。"""
    records = {hit.record_id for hit in result.evidence_hits if hit.record_id is not None}
    items = {
        hit.library_item_id
        for hit in result.evidence_hits
        if hit.record_id is None and hit.library_item_id is not None
    }
    return records, items, len(result.evidence_hits)


# ---------------------------------------------------------------------------
# 四档隔离失败即红（spec 硬门禁：scope 泄漏零容忍）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_record_scope_isolation(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        result = await search(
            app, RetrievalScope(scope=ChatScope.RECORD, record_id=REC_ML_AUDIO), "链式法则"
        )
        records, items, count = hit_quotas(result)
        assert count == 1 and records == {REC_ML_AUDIO} and not items
        # RECORD 边界：其它记录与资料直挂分片均不可见。
        other = await search(
            app, RetrievalScope(scope=ChatScope.RECORD, record_id=REC_ML_AUDIO), "网页剪藏正文"
        )
        assert other.evidence_hits == []
        # 软删记录目标：服务直调同样零命中（不越界兜底）。
        deleted = await search(
            app, RetrievalScope(scope=ChatScope.RECORD, record_id=REC_ML_DELETED), "支持向量机"
        )
        assert deleted.evidence_hits == []


@pytest.mark.anyio
async def test_library_item_scope_isolation(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        # 该资料（关联记录带分片）可命中关联记录原文。
        result = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_ML_AUDIO),
            "链式法则",
        )
        records, _items, count = hit_quotas(result)
        assert count == 1 and records == {REC_ML_AUDIO}
        # 同课程其它记录 / 其它条目直挂分片不得混入。
        leaked = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_ML_AUDIO),
            "B+ 树",
        )
        assert leaked.evidence_hits == []
        # 关联记录无分片（粘贴）：记录级 transcript 子串兜底继承（contract §4）。
        fallback = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_ML_TEXT),
            "讲给外行听",
        )
        assert len(fallback.evidence_hits) == 1
        assert fallback.evidence_hits[0].record_id == REC_ML_PASTE
        assert fallback.evidence_hits[0].channel == "transcript_fallback"
        assert "讲给外行听" in fallback.evidence_hits[0].quote
        # 关联记录已软删（挂在本条目上）：转写与文档分片都不得经关联边界漏入。
        linked_deleted = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_WEB),
            "支持向量机",
        )
        assert linked_deleted.evidence_hits == []
        linked_deleted_doc = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_WEB),
            "高维空间",
        )
        assert linked_deleted_doc.evidence_hits == []
        # 归档 / 软删条目作为目标：零命中。
        archived = await search(
            app,
            RetrievalScope(scope=ChatScope.LIBRARY_ITEM, library_item_id=ITEM_WEB_ARCHIVED),
            "归档资料正文",
        )
        assert archived.evidence_hits == []


@pytest.mark.anyio
async def test_course_scope_isolation(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        result = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML), "链式法则"
        )
        records, _items, count = hit_quotas(result)
        assert count == 1 and records == {REC_ML_AUDIO}
        # 不含其它课程与未归类全局资料。
        leaked = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML), "B+ 树"
        )
        assert leaked.evidence_hits == []
        unclassified = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML), "网页剪藏正文"
        )
        assert unclassified.evidence_hits == []
        # 软删记录即使在本课程内也不得命中。
        deleted = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML), "支持向量机"
        )
        assert deleted.evidence_hits == []
        # DB 课程内命中归属正确。
        db_hits = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_DB), "B+ 树"
        )
        db_records, _db_items, db_count = hit_quotas(db_hits)
        assert db_count == 1 and db_records == {REC_DB_DOC}


@pytest.mark.anyio
async def test_all_scope_includes_unclassified_and_excludes_dead_sources(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        # 未归类资料直挂分片仅 ALL 可见。
        result = await search(app, RetrievalScope(scope=ChatScope.ALL), "网页剪藏正文")
        _records, items, count = hit_quotas(result)
        assert count == 1 and items == {ITEM_WEB}
        hit = result.evidence_hits[0]
        assert hit.source_title == "网页剪藏正文"
        assert hit.source_type == "WEB"
        assert hit.channel == "fts"
        # 归档 / 软删资料不以资料身份召回（07 硬门禁）。
        archived = await search(app, RetrievalScope(scope=ChatScope.ALL), "归档资料正文")
        assert archived.evidence_hits == []
        deleted_item = await search(app, RetrievalScope(scope=ChatScope.ALL), "已删除资料正文")
        assert deleted_item.evidence_hits == []
        deleted_record = await search(app, RetrievalScope(scope=ChatScope.ALL), "支持向量机")
        assert deleted_record.evidence_hits == []
        # 软删记录的文档分片同样不得经 LEFT JOIN 记录路径漏入（r.id 防线）。
        deleted_doc = await search(app, RetrievalScope(scope=ChatScope.ALL), "高维空间")
        assert deleted_doc.evidence_hits == []
        deleted_course_doc = await search(
            app, RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML), "高维空间"
        )
        assert deleted_course_doc.evidence_hits == []
        # COURSE/ALL 无记录级子串兜底：无分片粘贴记录在 ALL 也不可检索（contract §4）。
        no_fallback = await search(app, RetrievalScope(scope=ChatScope.ALL), "讲给外行听")
        assert no_fallback.evidence_hits == []


@pytest.mark.anyio
async def test_evidence_shape_verbatim_and_window(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        result = await search(
            app, RetrievalScope(scope=ChatScope.RECORD, record_id=REC_ML_AUDIO), "链式法则"
        )
        hit = result.evidence_hits[0]
        assert hit.quote == "反向传播算法利用链式法则，把损失函数对每个参数的梯度逐层传回去。"
        assert hit.source_title == "梯度下降第 1 讲"
        assert hit.locator == {"time": "0:10-0:25"}
        assert hit.library_item_id == ITEM_ML_AUDIO  # 代表资料身份可解析
        assert hit.source_type == "AUDIO"


# ---------------------------------------------------------------------------
# 工具预算（contract §3 冻结值）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tool_budget_call_limit_and_truncation(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        context = LibrarySearchContext(
            scope=ChatScope.ALL,
            course_id=None,
            session_factory=app.state.session_factory,
            budget=ToolCallBudget(),
        )
        token = bind_library_context(context)
        try:
            payloads: list[dict[str, Any]] = [
                cast(
                    dict[str, Any],
                    json.loads(await search_library.ainvoke({"query": query})),
                )
                for query in (
                    "链式法则",
                    "B+ 树",
                    "网页剪藏正文",
                    "支持向量机",
                    "归档资料正文",
                    "已删除资料正文",
                )
            ]
            # 第 7 次调用被预算拒绝：不执行检索，提示基于已有结果回答。
            seventh = cast(
                dict[str, Any],
                json.loads(await search_library.ainvoke({"query": "链式法则"})),
            )
        finally:
            reset_library_context(token)
        assert context.budget.calls_used == MAX_TOOL_CALLS_PER_TURN
        assert seventh["evidence_hits"] == []
        assert "已达上限" in seventh["message"]
        # 每次载荷 ≤ 4000 字符（截断标记而非静默丢弃）。
        for payload in payloads:
            assert len(json.dumps(payload, ensure_ascii=False)) <= TOOL_RESULT_MAX_CHARS


@pytest.mark.anyio
async def test_tool_budget_cumulative_round_cap(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, _client):
        await seed_scope_corpus(app)
        budget = ToolCallBudget()
        budget.chars_fed = TOOL_ROUND_OUTPUT_MAX_CHARS  # 模拟本轮累计已满
        context = LibrarySearchContext(
            scope=ChatScope.ALL,
            course_id=None,
            session_factory=app.state.session_factory,
            budget=budget,
        )
        token = bind_library_context(context)
        try:
            import json

            payload = cast(
                dict[str, Any], json.loads(await search_library.ainvoke({"query": "链式法则"}))
            )
        finally:
            reset_library_context(token)
        assert payload["evidence_hits"] == []
        assert payload["truncated"] is True
        assert "累计已达上下文预算" in payload["message"]


# ---------------------------------------------------------------------------
# LIBRARY_ITEM 会话（创建守卫 + 失效只读）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_library_item_session_creation_guards(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (_app, client):
        await seed_scope_corpus(_app)
        # 正常创建：回显 scope 与 library_item_id。
        created = await client.post(
            "/api/chat-sessions",
            json={"scope": "LIBRARY_ITEM", "library_item_id": ITEM_ML_AUDIO},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["scope"] == "LIBRARY_ITEM"
        assert body["library_item_id"] == ITEM_ML_AUDIO
        assert body["course_id"] == COURSE_ML
        assert body["record_id"] is None
        # 不存在 → 404；软删 → 409 LIBRARY_ITEM_DELETED；归档 → 409 LIBRARY_ITEM_ARCHIVED。
        missing = await client.post(
            "/api/chat-sessions",
            json={
                "scope": "LIBRARY_ITEM",
                "library_item_id": "b0000000-0000-4000-8000-000000000099",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "LIBRARY_ITEM_NOT_FOUND"
        deleted = await client.post(
            "/api/chat-sessions",
            json={"scope": "LIBRARY_ITEM", "library_item_id": ITEM_WEB_DELETED},
        )
        assert deleted.status_code == 409
        assert deleted.json()["code"] == "LIBRARY_ITEM_DELETED"
        archived = await client.post(
            "/api/chat-sessions",
            json={"scope": "LIBRARY_ITEM", "library_item_id": ITEM_WEB_ARCHIVED},
        )
        assert archived.status_code == 409
        assert archived.json()["code"] == "LIBRARY_ITEM_ARCHIVED"
        # 挂载 id 校验矩阵：LIBRARY_ITEM 不接受 record_id。
        mixed = await client.post(
            "/api/chat-sessions",
            json={
                "scope": "LIBRARY_ITEM",
                "library_item_id": ITEM_ML_AUDIO,
                "record_id": REC_ML_AUDIO,
            },
        )
        assert mixed.status_code == 422
        # 其它范围不接受 library_item_id。
        leaked = await client.post(
            "/api/chat-sessions", json={"scope": "ALL", "library_item_id": ITEM_ML_AUDIO}
        )
        assert leaked.status_code == 422


@pytest.mark.anyio
async def test_library_item_session_readonly_when_archived(tmp_path: Path) -> None:
    async with retrieval_app(tmp_path) as (app, client):
        # 发送校验顺序：先供应商（受理前置）再会话失效态，须配置供应商以触达守卫。
        save_llm_provider(
            tmp_path,
            base_url="https://stub.example.com/v1",
            api_key="sk-test",
            model="stub-chat-model",
            clear_api_key=False,
        )
        await seed_scope_corpus(app)
        created = await client.post(
            "/api/chat-sessions",
            json={"scope": "LIBRARY_ITEM", "library_item_id": ITEM_WEB},
        )
        session_id = cast(str, created.json()["id"])
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE library_items SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": ITEM_WEB},
            )
        # 失效态派生：列表/详情只读标记 + 发送被拒（409 稳定错误码）。
        detail = await client.get(f"/api/chat-sessions/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["library_item_deleted"] is True
        listing = await client.get("/api/chat-sessions")
        mine = next(item for item in listing.json() if item["id"] == session_id)
        assert mine["library_item_deleted"] is True
        sent = await client.post(
            f"/api/chat-sessions/{session_id}/messages", json={"content": "还在吗"}
        )
        assert sent.status_code == 409
        assert sent.json()["code"] == "CHAT_LIBRARY_ITEM_UNAVAILABLE"


# ---------------------------------------------------------------------------
# library 引用条目（资料直挂正文逐字校验，record 优先裁定）
# ---------------------------------------------------------------------------


def test_parse_library_citation_reply_library_entries() -> None:
    records = [
        LibraryRecordMaterial(
            record_id="rec-1",
            title="第 2 讲 一致性哈希",
            transcript="第二讲聚焦一致性哈希的实践应用。",
        )
    ]
    items = [
        LibraryItemMaterial(
            library_item_id="item-web",
            title="网页剪藏正文",
            content="网页剪藏正文记录了向量检索的取舍。",
        )
    ]
    text = (
        "向量检索讲取舍[1]，一致性哈希看实践[2]。\n"
        "[1] 网页剪藏正文记录了向量检索的取舍（来源：网页剪藏正文）\n"
        "[2] 第二讲聚焦一致性哈希的实践应用（来源：第 2 讲 一致性哈希）"
    )
    parsed = parse_library_citation_reply(text, records, items)
    assert parsed.citations == [
        {
            "index": 1,
            "source": "library",
            "library_item_id": "item-web",
            "title": "网页剪藏正文",
            "quote": "网页剪藏正文记录了向量检索的取舍",
        },
        {
            "index": 2,
            "source": "record",
            "record_id": "rec-1",
            "record_title": "第 2 讲 一致性哈希",
            "quote": "第二讲聚焦一致性哈希的实践应用",
        },
    ]
    # 逐字不过且无来源标记：丢弃，不得编造归属。
    bad = parse_library_citation_reply("正文\n[1] 语料中不存在的摘录", records, items)
    assert bad.citations == []


def test_parse_library_citation_reply_same_title_prefers_record() -> None:
    """回填条目与记录同标题：命中记录转写的落 record 条目（转写定位跳转更精确）。"""
    record = LibraryRecordMaterial(
        record_id="rec-1", title="同名资料", transcript="记录转写中的原句。"
    )
    item = LibraryItemMaterial(
        library_item_id="item-1", title="同名资料", content="资料直挂正文的原句。"
    )
    parsed = parse_library_citation_reply(
        "正文\n[1] 记录转写中的原句（来源：同名资料）\n[2] 资料直挂正文的原句（来源：同名资料）",
        [record],
        [item],
    )
    assert [entry["source"] for entry in parsed.citations] == ["record", "library"]
    assert parsed.citations[0]["record_id"] == "rec-1"
    assert parsed.citations[1]["library_item_id"] == "item-1"
