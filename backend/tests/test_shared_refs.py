"""共享来源引用（通用 Agent 第三阶段工单 05）：迁移结构、失效查询期派生、
引用增删查路由、检索覆盖（COURSE 档纳入被引用资料）、资产只读防线与
Agent 工具确认行为。"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import Token
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations, supported_user_version
from app.modules.agent.citations import parse_library_citation_reply
from app.modules.agent.message_service import (
    _load_scope_materials,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatScope
from app.modules.agent.tools.add_shared_ref import add_shared_ref
from app.modules.agent.tools.list_shared_refs import list_shared_refs
from app.modules.agent.tools.remove_shared_ref import remove_shared_ref
from app.modules.library.models import CourseSharedRef
from app.modules.library.proposals import ProposalService
from app.modules.library.retrieval import LibraryRetrievalService, RetrievalScope
from app.modules.library.shared_refs import SharedRefService, guard_asset_generation
from app.modules.search.segment_service import (
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.settings.config import save_llm_provider
from app.modules.transcript.sentences import content_hash
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"
NOW = "2026-09-30T08:00:00.000000Z"

COURSE_ML = "d0000000-0000-4000-8000-000000000001"
COURSE_AGENT = "d0000000-0000-4000-8000-000000000002"
COURSE_DB = "d0000000-0000-4000-8000-000000000003"

REC_ML_PAPER = "d0000000-0000-4000-8000-000000000011"
ITEM_ML_PAPER = "d0000000-0000-4000-8000-000000000021"
ITEM_ML_WEB = "d0000000-0000-4000-8000-000000000022"
REC_AGENT_NOTE = "d0000000-0000-4000-8000-000000000012"
REC_ML_TEXT = "d0000000-0000-4000-8000-000000000013"
ITEM_ML_TEXT = "d0000000-0000-4000-8000-000000000023"
TEXT_NEEDLE = "变分自编码器的重参数化技巧"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


@asynccontextmanager
async def app_client(tmp_path: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    from app.main import create_app

    data_dir = tmp_path / "KnowRealm"
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await app.state.course_tombstone_cleanup_task
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def run_sql(
    sql: str,
    params: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_full_corpus(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """ML 空间：论文条目（record 挂靠 + 直挂分片双路径）、纯文本条目（无分片
    粘贴形态）与已删网页条目；AGENT 空间：引用论文条目 + 自己的速记；DB 空间：
    隔离对照（零引用）。"""
    for course_id, name in (
        (COURSE_ML, "机器学习导论"),
        (COURSE_AGENT, "Agent 工程"),
        (COURSE_DB, "数据库系统"),
    ):
        await run_sql(
            "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
            "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)",
            {"id": course_id, "name": name, "now": NOW},
            session_factory,
        )
    # 论文条目（归属 ML）+ 挂靠 record（带转写分片）。
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash, "
        "metadata_json, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'WEB', '梯度下降论文', :hash, '{}', 'ACTIVE', :now, :now)",
        {"id": ITEM_ML_PAPER, "course_id": COURSE_ML, "hash": f"hash-{ITEM_ML_PAPER}", "now": NOW},
        session_factory,
    )
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) VALUES (:id, :course_id, 'AUDIO_IMPORT', '论文精读', "
        "'SUMMARY_PENDING', 60000, :now, :now)",
        {"id": REC_ML_PAPER, "course_id": COURSE_ML, "now": NOW},
        session_factory,
    )
    await run_sql(
        "INSERT INTO library_item_records (library_item_id, record_id, role, sequence_no, "
        "created_at) VALUES (:item_id, :record_id, 'PRIMARY', 0, :now)",
        {"item_id": ITEM_ML_PAPER, "record_id": REC_ML_PAPER, "now": NOW},
        session_factory,
    )
    # 网页条目（归属 ML）：直挂分片（03 剪藏形态）。
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash, "
        "metadata_json, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'WEB', '注意力机制综述', :hash, '{}', 'ACTIVE', :now, :now)",
        {"id": ITEM_ML_WEB, "course_id": COURSE_ML, "hash": f"hash-{ITEM_ML_WEB}", "now": NOW},
        session_factory,
    )
    # 纯文本条目（归属 ML）：无分片粘贴形态（record 挂靠、零分片——正文只在
    # transcript，FTS 永不命中，兜底路径语料）。
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash, "
        "metadata_json, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'TEXT', 'VAE 学习笔记', :hash, '{}', 'ACTIVE', :now, :now)",
        {"id": ITEM_ML_TEXT, "course_id": COURSE_ML, "hash": f"hash-{ITEM_ML_TEXT}", "now": NOW},
        session_factory,
    )
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) VALUES (:id, :course_id, 'PASTE', 'VAE 学习笔记', "
        "'COMPLETED', 0, :now, :now)",
        {"id": REC_ML_TEXT, "course_id": COURSE_ML, "now": NOW},
        session_factory,
    )
    await run_sql(
        "INSERT INTO transcripts (id, record_id, language, content, source_version, "
        "edited_by_user, created_at, updated_at) VALUES (:id, :record_id, 'zh-CN', "
        ":content, 1, 0, :now, :now)",
        {
            "id": f"transcript-{REC_ML_TEXT}",
            "record_id": REC_ML_TEXT,
            "content": f"{TEXT_NEEDLE}用于稳定训练。",
            "now": NOW,
        },
        session_factory,
    )
    await run_sql(
        "INSERT INTO library_item_records (library_item_id, record_id, role, sequence_no, "
        "created_at) VALUES (:item_id, :record_id, 'PRIMARY', 0, :now)",
        {"item_id": ITEM_ML_TEXT, "record_id": REC_ML_TEXT, "now": NOW},
        session_factory,
    )
    # AGENT 自己的记录（本课程命中对照）。
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) VALUES (:id, :course_id, 'QUICK_NOTE', '智能体笔记', "
        "'COMPLETED', 60000, :now, :now)",
        {"id": REC_AGENT_NOTE, "course_id": COURSE_AGENT, "now": NOW},
        session_factory,
    )
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                "created_at, updated_at) VALUES (:id, :record_id, 'AUDIO', 'RECORDED', "
                "'p.ogg', 'p.ogg', 'audio/ogg', 1, 60000, 0, 'h', :now, :now)"
            ),
            {"id": f"file-{REC_ML_PAPER}", "record_id": REC_ML_PAPER, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at) VALUES (:id, :record_id, 'zh-CN', "
                ":content, 1, 0, :now, :now)"
            ),
            {
                "id": f"transcript-{REC_ML_PAPER}",
                "record_id": REC_ML_PAPER,
                "content": "梯度下降通过反向传播迭代更新参数。",
                "now": NOW,
            },
        )
        # AGENT 本课程速记的转写（材料与引用校验的本课程命中对照）。
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at) VALUES (:id, :record_id, 'zh-CN', "
                ":content, 1, 0, :now, :now)"
            ),
            {
                "id": f"transcript-{REC_AGENT_NOTE}",
                "record_id": REC_AGENT_NOTE,
                "content": "智能体通过工具调用完成多步任务。",
                "now": NOW,
            },
        )
        await session.execute(
            text(
                "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                "speaker, content, content_hash) VALUES (:id, :transcript_id, :record_id, "
                ":file_id, 0, 10000, 25000, 10000, 25000, NULL, :content, :chash)"
            ),
            {
                "id": f"seg-{REC_ML_PAPER}",
                "transcript_id": f"transcript-{REC_ML_PAPER}",
                "record_id": REC_ML_PAPER,
                "file_id": f"file-{REC_ML_PAPER}",
                "content": "梯度下降通过反向传播迭代更新参数。",
                "chash": content_hash("梯度下降通过反向传播迭代更新参数。"),
            },
        )
        await session.execute(
            text(
                "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                "library_item_id, sequence_no, page_no, section_title, content, start_offset, "
                "end_offset, content_hash) VALUES (:id, NULL, NULL, NULL, :item_id, 0, NULL, "
                "NULL, :content, 0, 0, :chash)"
            ),
            {
                "id": f"{ITEM_ML_WEB}-seg-0",
                "item_id": ITEM_ML_WEB,
                "content": "注意力机制用查询键值计算加权求和。",
                "chash": content_hash("注意力机制用查询键值计算加权求和。"),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, [f"seg-{REC_ML_PAPER}"]
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, [f"{ITEM_ML_WEB}-seg-0"]
        )


async def seed_ref(
    session_factory: async_sessionmaker[AsyncSession], course_id: str, item_id: str
) -> str:
    ref_id = uuid4().hex
    await run_sql(
        "INSERT INTO course_shared_refs (id, course_id, library_item_id, created_at) "
        "VALUES (:id, :course_id, :item_id, :now)",
        {"id": ref_id, "course_id": course_id, "item_id": item_id, "now": NOW},
        session_factory,
    )
    return ref_id


# ---------------------------------------------------------------------------
# 迁移结构（0037）。


@pytest.mark.anyio
async def test_migration_0037_creates_course_shared_refs(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(course_shared_refs)")
            ).fetchall()
        }
        indexes = {
            (cast(str, row[1]), bool(row[2]), cast(str, row[3]), cast(str, row[4]))
            for row in await (
                await connection.execute("PRAGMA index_list(course_shared_refs)")
            ).fetchall()
        }
        # PRAGMA foreign_key_list 列序：5=on_update、6=on_delete（实测 SQLite 3.4x）。
        foreign_keys = sorted(
            (cast(str, row[2]), cast(str, row[6]))
            for row in await (
                await connection.execute("PRAGMA foreign_key_list(course_shared_refs)")
            ).fetchall()
        )

    assert columns == {"id", "course_id", "library_item_id", "created_at"}
    # UNIQUE(course_id, library_item_id)：autoindex，origin='u'、unique=1。
    assert ("sqlite_autoindex_course_shared_refs_2", True, "u", 0) in indexes
    assert ("idx_course_shared_refs_item", False, "c", 0) in indexes
    assert foreign_keys == [("courses", "CASCADE"), ("library_items", "CASCADE")]

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
    assert version == (supported_user_version(),)


@pytest.mark.anyio
async def test_unique_rejects_duplicate_ref(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        with pytest.raises(IntegrityError):
            await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)


# ---------------------------------------------------------------------------
# 路由生命周期：ingest 建条目 → 引用 → 软删失效派生 → 恢复复活 → 删除引用。


@pytest.mark.anyio
async def test_ref_routes_lifecycle(tmp_path: Path) -> None:
    async with app_client(tmp_path) as (_app, client):
        course = await client.post(
            "/api/courses",
            json={"name": "Agent 工程", "learning_context": "INTEREST", "depth": "INTERMEDIATE"},
        )
        assert course.status_code == 201
        course_id = course.json()["id"]

        created = await client.post(
            "/api/library/ingest",
            json={"source": "text", "title": "梯度下降论文", "content": "正文内容。"},
        )
        assert created.status_code == 202
        item_id = created.json()["item"]["id"]
        assert created.json()["item"]["course_id"] is None

        # 未归类条目可直接被引用（归属与本课程不同即可）。
        added = await client.post(
            f"/api/courses/{course_id}/shared-refs", json={"library_item_id": item_id}
        )
        assert added.status_code == 201
        body = added.json()
        assert body["library_item_id"] == item_id
        assert body["available"] is True
        assert body["owner_course_id"] is None

        listed = await client.get(f"/api/courses/{course_id}/shared-refs")
        assert listed.status_code == 200
        rows = [row for row in listed.json() if row["library_item_id"] == item_id]
        assert len(rows) == 1

        # 条目软删 → 引用失效（查询期派生）；引用行保留，仍可删除。
        soft_deleted = await client.delete(f"/api/library/items/{item_id}")
        assert soft_deleted.status_code == 200
        relisted = await client.get(f"/api/courses/{course_id}/shared-refs")
        stale = [row for row in relisted.json() if row["library_item_id"] == item_id]
        assert stale[0]["available"] is False

        # 回收站恢复 → 引用自动复活。
        restored = await client.post(f"/api/library/items/{item_id}/restore")
        assert restored.status_code == 200
        revived = await client.get(f"/api/courses/{course_id}/shared-refs")
        alive = [row for row in revived.json() if row["library_item_id"] == item_id]
        assert alive[0]["available"] is True

        removed = await client.delete(f"/api/courses/{course_id}/shared-refs/{item_id}")
        assert removed.status_code == 204
        again = await client.delete(f"/api/courses/{course_id}/shared-refs/{item_id}")
        assert again.status_code == 404
        assert again.json()["code"] == "SHARED_REF_NOT_FOUND"

        # 课程不可见：404。
        missing = await client.get(f"/api/courses/{COURSE_DB[:-1]}f/shared-refs")
        assert missing.status_code == 404
        assert missing.json()["code"] == "COURSE_NOT_FOUND"


@pytest.mark.anyio
async def test_add_validation_rejections(tmp_path: Path) -> None:
    async with app_client(tmp_path) as (_app, client):
        await seed_full_corpus(_app.state.session_factory)
        # 课程不存在。
        unknown_course = await client.post(
            f"/api/courses/{COURSE_DB[:-1]}f/shared-refs",
            json={"library_item_id": ITEM_ML_PAPER},
        )
        assert unknown_course.status_code == 404
        assert unknown_course.json()["code"] == "COURSE_NOT_FOUND"
        # 条目不存在。
        unknown_item = await client.post(
            f"/api/courses/{COURSE_AGENT}/shared-refs",
            json={"library_item_id": ITEM_ML_PAPER[:-1] + "f"},
        )
        assert unknown_item.status_code == 404
        assert unknown_item.json()["code"] == "LIBRARY_ITEM_NOT_FOUND"
        # 已归属本课程：无需引用。
        owned = await client.post(
            f"/api/courses/{COURSE_ML}/shared-refs", json={"library_item_id": ITEM_ML_PAPER}
        )
        assert owned.status_code == 409
        assert owned.json()["code"] == "SHARED_REF_ITEM_OWNED"
        # 重复引用。
        assert (
            await client.post(
                f"/api/courses/{COURSE_AGENT}/shared-refs",
                json={"library_item_id": ITEM_ML_PAPER},
            )
        ).status_code == 201
        duplicate = await client.post(
            f"/api/courses/{COURSE_AGENT}/shared-refs", json={"library_item_id": ITEM_ML_PAPER}
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "SHARED_REF_DUPLICATE"


@pytest.mark.anyio
async def test_physical_delete_cascades_and_owner_migration_keeps_ref(
    tmp_path: Path,
) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_WEB)

        # 归属迁移不影响引用（引用是两个空间的直接关系）。
        await run_sql(
            "UPDATE library_items SET course_id = :course_id WHERE id = :item_id",
            {"course_id": COURSE_DB, "item_id": ITEM_ML_WEB},
            session_factory,
        )
        count = await _scalar(
            session_factory,
            "SELECT COUNT(*) FROM course_shared_refs WHERE course_id = :c AND library_item_id = :i",
            {"c": COURSE_AGENT, "i": ITEM_ML_WEB},
        )
        assert count == 1

        # 条目物理删除 → 引用行级联清理。
        await run_sql(
            "DELETE FROM library_items WHERE id = :item_id",
            {"item_id": ITEM_ML_WEB},
            session_factory,
        )
        count = await _scalar(
            session_factory,
            "SELECT COUNT(*) FROM course_shared_refs WHERE library_item_id = :i",
            {"i": ITEM_ML_WEB},
        )
        assert count == 0


async def _scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str, params: dict[str, object]
) -> Any:
    async with session_factory() as session:
        return (await session.execute(text(sql), params)).scalar_one()


# ---------------------------------------------------------------------------
# 检索覆盖：COURSE 档纳入被引用资料（record 分片 + 条目直挂分片 + asset 导航）。


@pytest.mark.anyio
async def test_retrieval_shared_coverage_and_isolation(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_WEB)

        async with session_factory() as session:
            result = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                "梯度下降 反向传播",
            )
        hits = {hit.record_id: hit for hit in result.evidence_hits}
        assert REC_ML_PAPER in hits  # 共享 record 经条目覆盖进入
        assert hits[REC_ML_PAPER].shared_source is True

        async with session_factory() as session:
            web_result = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                "注意力机制 加权求和",
            )
        web_hits = [hit for hit in web_result.evidence_hits if hit.library_item_id == ITEM_ML_WEB]
        assert web_hits and web_hits[0].shared_source is True

        # asset 导航命中覆盖共享条目与记录。
        async with session_factory() as session:
            assets = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                "论文",
            )
        asset_ids = {match.id for match in assets.asset_matches}
        assert ITEM_ML_PAPER in asset_ids or REC_ML_PAPER in asset_ids

        # 隔离：无引用的课程检索不到 ML 资料。
        async with session_factory() as session:
            isolated = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_DB),
                "梯度下降",
            )
        assert isolated.evidence_hits == []

        # 原空间视角（ML）检索自己资料：不标共享。
        async with session_factory() as session:
            own = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_ML),
                "梯度下降 反向传播",
            )
        own_hits = [hit for hit in own.evidence_hits if hit.record_id == REC_ML_PAPER]
        assert own_hits and own_hits[0].shared_source is False


@pytest.mark.anyio
async def test_retrieval_shared_segmentless_text_fallback(tmp_path: Path) -> None:
    """共享的无分片纯文本资料经记录级兜底进入 COURSE 检索（spec：被引用资料
    的 Record 内容进入课程问答与检索——粘贴形态正文只在 transcript，FTS 分片
    路径永不命中）；本课程自己的无分片记录维持 contract §4 不兜底口径。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_TEXT)

        async with session_factory() as session:
            result = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                TEXT_NEEDLE,
            )
        hits = [hit for hit in result.evidence_hits if hit.record_id == REC_ML_TEXT]
        assert hits
        assert hits[0].channel == "transcript_fallback"
        assert hits[0].shared_source is True
        assert TEXT_NEEDLE in hits[0].quote

        # 无引用课程隔离：兜底路径同样检索不到。
        async with session_factory() as session:
            isolated = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_DB),
                TEXT_NEEDLE,
            )
        assert isolated.evidence_hits == []

        # 本课程自己的无分片记录（速记）不进兜底（contract §4 口径不扩大）。
        async with session_factory() as session:
            own_note = await LibraryRetrievalService.search(
                session,
                RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                "智能体通过工具调用",
            )
        assert own_note.evidence_hits == []


@pytest.mark.anyio
async def test_retrieval_soft_delete_invalidates_and_restore_revives(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)

        async def agent_hits() -> int:
            async with session_factory() as session:
                result = await LibraryRetrievalService.search(
                    session,
                    RetrievalScope(scope=ChatScope.COURSE, course_id=COURSE_AGENT),
                    "梯度下降 反向传播",
                )
            return len(result.evidence_hits)

        assert await agent_hits() > 0
        await run_sql(
            "UPDATE library_items SET deleted_at = :at WHERE id = :item_id",
            {"at": NOW, "item_id": ITEM_ML_PAPER},
            session_factory,
        )
        assert await agent_hits() == 0
        await run_sql(
            "UPDATE library_items SET deleted_at = NULL WHERE id = :item_id",
            {"item_id": ITEM_ML_PAPER},
            session_factory,
        )
        assert await agent_hits() > 0


@pytest.mark.anyio
async def test_scope_materials_and_citations_shared_flag(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_WEB)

        async with session_factory() as session:
            records, items = await _load_scope_materials(session, ChatScope.COURSE, COURSE_AGENT)
        record_map = {material.record_id: material for material in records}
        assert record_map[REC_ML_PAPER].shared is True
        assert record_map[REC_AGENT_NOTE].shared is False
        item_map = {material.library_item_id: material for material in items}
        assert item_map[ITEM_ML_WEB].shared is True

        reply = (
            "正文。\n[1] 梯度下降通过反向传播迭代更新参数。（来源：论文精读）\n"
            "[2] 注意力机制用查询键值计算加权求和。（来源：注意力机制综述）\n"
            "[3] 智能体通过工具调用完成多步任务。（来源：智能体笔记）"
        )
        parsed = parse_library_citation_reply(reply, records, items)
        by_index = {cast(int, citation["index"]): citation for citation in parsed.citations}
        assert by_index[1]["shared"] is True  # 共享记录
        assert by_index[2]["shared"] is True  # 共享条目直挂正文
        assert "shared" not in by_index[3]  # 本课程命中不带标志


# ---------------------------------------------------------------------------
# 资产只读防线（SHARED_REF_ASSET_READ_ONLY）。


@pytest.mark.anyio
async def test_guard_asset_generation_semantics(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)

        async with session_factory() as session:
            # 无上下文 / 本课程上下文：放行（原空间视角生成是合法能力）。
            await guard_asset_generation(session, REC_ML_PAPER, None)
            await guard_asset_generation(session, REC_ML_PAPER, COURSE_ML)
            # 共享上下文：拒绝。
            with pytest.raises(CodedHTTPException) as rejected:
                await guard_asset_generation(session, REC_ML_PAPER, COURSE_AGENT)
            assert rejected.value.code == "SHARED_REF_ASSET_READ_ONLY"
            # 无关上下文（DB 未引用该资料）：放行，不越权拦截。
            await guard_asset_generation(session, REC_ML_PAPER, COURSE_DB)
            # 条目软删 → 引用失效 → 放行（只读防线随失效派生同步退出）。
            await session.execute(
                text("UPDATE library_items SET deleted_at = :at WHERE id = :item_id"),
                {"at": NOW, "item_id": ITEM_ML_PAPER},
            )
            await guard_asset_generation(session, REC_ML_PAPER, COURSE_AGENT)
            # record 不存在：跳过（交由既有 RECORD_NOT_FOUND 执法）。
            await guard_asset_generation(session, REC_ML_PAPER[:-1] + "f", COURSE_AGENT)


@pytest.mark.anyio
async def test_summary_submit_rejects_shared_context(tmp_path: Path) -> None:
    async with app_client(tmp_path) as (app, client):
        await seed_full_corpus(app.state.session_factory)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        save_llm_provider(
            app.state.data_dir,
            base_url="https://example.invalid/v1",
            api_key="sk-test",
            model="test-model",
            clear_api_key=False,
        )
        consent = await client.post("/api/settings/external-processing-consents/llm")
        assert consent.status_code == 200

        rejected = await client.post(
            f"/api/records/{REC_ML_PAPER}/summary-jobs", params={"course_id": COURSE_AGENT}
        )
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "SHARED_REF_ASSET_READ_ONLY"

        # 原空间 / 无上下文照常提交（202）。
        allowed = await client.post(
            f"/api/records/{REC_ML_PAPER}/summary-jobs", params={"course_id": COURSE_ML}
        )
        assert allowed.status_code == 202, allowed.json()


# ---------------------------------------------------------------------------
# Agent 工具：确认卡提案流 + 提交期拒绝 + 只读清单载荷。


@pytest.mark.anyio
async def test_agent_shared_ref_tools(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory,
                session_id="sess-shared-refs",
                auth_mode=AuthMode.REQUEST_APPROVAL,
                budget=ToolCallBudget(),
            )
        )
        try:
            # add：落 PENDING 提案（默认档确认卡）。
            raw = await add_shared_ref.ainvoke(
                {"course_id": COURSE_AGENT, "library_item_id": ITEM_ML_PAPER}
            )
            payload = dict(json.loads(raw))
            assert payload["ok"] is True
            assert payload["proposals"][0]["action"] == "add_shared_ref"
            assert payload["proposals"][0]["status"] == "PENDING"

            # 已归属本课程：提交期结构化拒绝（零提案）。
            raw = await add_shared_ref.ainvoke(
                {"course_id": COURSE_ML, "library_item_id": ITEM_ML_PAPER}
            )
            assert dict(json.loads(raw))["error"] == "SHARED_REF_ITEM_OWNED"

            # remove：引用尚不存在 → 结构化拒绝。
            raw = await remove_shared_ref.ainvoke(
                {"course_id": COURSE_AGENT, "library_item_id": ITEM_ML_WEB}
            )
            assert dict(json.loads(raw))["error"] == "SHARED_REF_NOT_FOUND"

            # list：确认卡尚未确认，清单如实为零；课程不存在结构化说明。
            raw = await list_shared_refs.ainvoke({"course_id": COURSE_AGENT})
            listed = dict(json.loads(raw))
            assert listed["ok"] is True
            assert listed["shared_refs"] == []
            raw = await list_shared_refs.ainvoke({"course_id": COURSE_DB[:-1] + "f"})
            assert dict(json.loads(raw))["ok"] is False
        finally:
            reset_agent_runtime_context(token)

        # 直接落引用行后 list 可见（模拟确认后状态）。
        await seed_ref(session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory,
                session_id="sess-shared-refs",
                auth_mode=AuthMode.REQUEST_APPROVAL,
                budget=ToolCallBudget(),
            )
        )
        try:
            raw = await list_shared_refs.ainvoke({"course_id": COURSE_AGENT})
            listed = dict(json.loads(raw))
            assert listed["ok"] is True
            entry = listed["shared_refs"][0]
            assert entry["library_item_id"] == ITEM_ML_PAPER
            assert entry["available"] is True
            assert entry["owner_course_name"] == "机器学习导论"

            # remove：已有引用 → 落 PENDING 提案。
            raw = await remove_shared_ref.ainvoke(
                {"course_id": COURSE_AGENT, "library_item_id": ITEM_ML_PAPER}
            )
            payload = dict(json.loads(raw))
            assert payload["ok"] is True
            assert payload["proposals"][0]["action"] == "remove_shared_ref"
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_remove_proposal_stale_after_ref_recreate(tmp_path: Path) -> None:
    """移除提案快照绑定引用行 id（ADR-0026 对象版本确认）：确认窗口内引用被
    删重建（行身份变化）→ 旧提案 OPERATION_SNAPSHOT_STALE 失效，不得删除新
    引用行；快照未变的正常确认照常删除。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        async with session_factory() as session, session.begin():
            await SharedRefService.add_core(session, COURSE_AGENT, ITEM_ML_PAPER)

        async def bind() -> Token[AgentRuntimeContext | None]:
            return bind_agent_runtime_context(
                AgentRuntimeContext(
                    session_factory=session_factory,
                    session_id="sess-remove-stale",
                    auth_mode=AuthMode.REQUEST_APPROVAL,
                    budget=ToolCallBudget(),
                )
            )

        async def submit_remove() -> str:
            token = await bind()
            try:
                raw = await remove_shared_ref.ainvoke(
                    {"course_id": COURSE_AGENT, "library_item_id": ITEM_ML_PAPER}
                )
            finally:
                reset_agent_runtime_context(token)
            proposals = dict(json.loads(raw))["proposals"]
            assert proposals, "remove 工具应落提案"
            return cast(str, proposals[0]["proposal_id"])

        async def current_ref_id() -> str | None:
            async with session_factory() as session:
                return await session.scalar(
                    select(CourseSharedRef.id).where(
                        CourseSharedRef.course_id == COURSE_AGENT,
                        CourseSharedRef.library_item_id == ITEM_ML_PAPER,
                    )
                )

        # 正常路径对照：快照未变 → 确认成功删除引用行。
        proposal_a = await submit_remove()
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_a)
        assert confirmed.status == "APPLIED"
        assert confirmed.snapshot is not None
        assert confirmed.snapshot["course_name"] == "Agent 工程"
        assert await current_ref_id() is None

        # 确认窗口内删了重建（行身份变化）→ 旧提案失效、新引用行保留。
        async with session_factory() as session, session.begin():
            await SharedRefService.add_core(session, COURSE_AGENT, ITEM_ML_PAPER)
        recreated_id = await current_ref_id()
        assert recreated_id is not None
        proposal_b = await submit_remove()
        async with session_factory() as session, session.begin():
            await SharedRefService.remove_core(session, COURSE_AGENT, ITEM_ML_PAPER)
        async with session_factory() as session, session.begin():
            await SharedRefService.add_core(session, COURSE_AGENT, ITEM_ML_PAPER)
        assert await current_ref_id() not in (None, recreated_id)

        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_b)
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        assert await current_ref_id() is not None  # 新引用行未被旧批准删除
        async with session_factory() as session:
            stale = await ProposalService._get(session, proposal_b)  # pyright: ignore[reportPrivateUsage]
        assert stale.status == "FAILED"
