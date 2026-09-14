"""分片 FTS5 检索索引（票 01）：迁移 0020、同事务 upsert 幂等、编辑重切索引同步、
回表过滤软删与失效 transcript、启动回填幂等、finalizer 建分片即可检索。"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.search.schemas import SegmentEntityType, SegmentSearchHit
from app.modules.search.segment_service import (
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-13T08:00:00.000000Z"


@asynccontextmanager
async def running_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def seed_record(
    app: FastAPI,
    record_id: str,
    title: str,
    *,
    capture_type: str = "RECORDING",
    deleted_at: str | None = None,
    course_id: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, :capture_type, :title, 'COMPLETED', 60000, NULL, "
                ":now, :now, :deleted_at)"
            ),
            {
                "id": record_id,
                "course_id": course_id,
                "capture_type": capture_type,
                "title": title,
                "now": NOW,
                "deleted_at": deleted_at,
            },
        )


async def seed_record_file(app: FastAPI, record_id: str, file_id: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', 'audio/ogg', "
                "1, 60000, 0, 'h', :now, :now, NULL)"
            ),
            {"id": file_id, "record_id": record_id, "now": NOW},
        )


async def seed_transcript(app: FastAPI, record_id: str, transcript_id: str, content: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)"
            ),
            {"id": transcript_id, "record_id": record_id, "content": content, "now": NOW},
        )


async def seed_transcript_segment(
    app: FastAPI,
    *,
    segment_id: str,
    transcript_id: str,
    record_id: str,
    file_id: str,
    sequence_no: int,
    content: str,
    record_start_ms: int | None = None,
    record_end_ms: int | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                "speaker, content, content_hash) "
                "VALUES (:id, :transcript_id, :record_id, :file_id, :sequence_no, "
                ":record_start_ms, :record_end_ms, :record_start_ms, :record_end_ms, "
                "NULL, :content, :content_hash)"
            ),
            {
                "id": segment_id,
                "transcript_id": transcript_id,
                "record_id": record_id,
                "file_id": file_id,
                "sequence_no": sequence_no,
                "record_start_ms": record_start_ms,
                "record_end_ms": record_end_ms,
                "content": content,
                "content_hash": content_hash(content),
            },
        )


async def seed_document_segment(
    app: FastAPI,
    *,
    segment_id: str,
    record_id: str,
    file_id: str,
    sequence_no: int,
    content: str,
    page_no: int | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                "course_material_id, sequence_no, page_no, section_title, content, "
                "start_offset, end_offset, content_hash) "
                "VALUES (:id, NULL, :record_id, :file_id, NULL, :sequence_no, :page_no, "
                "NULL, :content, 0, 0, :content_hash)"
            ),
            {
                "id": segment_id,
                "record_id": record_id,
                "file_id": file_id,
                "sequence_no": sequence_no,
                "page_no": page_no,
                "content": content,
                "content_hash": content_hash(content),
            },
        )


async def upsert_index(
    app: FastAPI, entity_type: SegmentEntityType, segment_ids: list[str]
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await SegmentSearchService.upsert_segment_index(session, entity_type, segment_ids)


async def search_hits(
    app: FastAPI, record_id: str, query: str, limit: int = 8
) -> list[SegmentSearchHit]:
    async with app.state.session_factory() as session:
        return await SegmentSearchService.search_segments(session, record_id, query, limit)


async def index_row_count(app: FastAPI) -> int:
    async with app.state.session_factory() as session:
        return int(await session.scalar(text("SELECT count(*) FROM segment_search_index")) or 0)


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
async def test_migration_0020_creates_segment_search_index(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    db_path = data_dir / "knowrealm.db"
    data_dir.mkdir()
    from app.db.migrations import run_migrations

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        tables = {
            row[0]
            for row in await (
                await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        columns = [
            row[1]
            for row in await (
                await connection.execute("PRAGMA table_info(segment_search_index)")
            ).fetchall()
        ]

    assert version == (22,)
    assert "segment_search_index" in tables
    assert columns == ["body", "entity_type", "entity_id"]


@pytest.mark.anyio
async def test_upsert_is_idempotent_and_hits_verbatim_content(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        record_id = "22222222-2222-4222-8222-222222222222"
        transcript_id = "33333333-3333-4333-8333-333333333333"
        file_id = "44444444-4444-4444-8444-444444444444"
        determinant_id = "55555555-5555-4555-8555-555555555555"
        eigen_id = "66666666-6666-4666-8666-666666666666"
        await seed_record(app, record_id, "线性代数第一讲")
        await seed_record_file(app, record_id, file_id)
        await seed_transcript(app, record_id, transcript_id, "正文")
        await seed_transcript_segment(
            app,
            segment_id=determinant_id,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=0,
            content="本讲介绍行列式的计算方法",
            record_start_ms=1_000,
            record_end_ms=20_000,
        )
        await seed_transcript_segment(
            app,
            segment_id=eigen_id,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=1,
            content="特征值与特征向量的几何意义",
            record_start_ms=20_000,
            record_end_ms=40_000,
        )
        await upsert_index(app, ENTITY_TRANSCRIPT_SEGMENT, [determinant_id, eigen_id])
        assert await index_row_count(app) == 2

        # 重复 upsert：先删后插，同事务幂等不重复插行。
        await upsert_index(app, ENTITY_TRANSCRIPT_SEGMENT, [determinant_id, eigen_id])
        assert await index_row_count(app) == 2

        hits = await search_hits(app, record_id, "行列式")

    assert [hit.segment_id for hit in hits] == [determinant_id]
    assert hits[0].entity_type == "transcript_segment"
    assert hits[0].content == "本讲介绍行列式的计算方法"
    assert hits[0].sequence_no == 0
    assert hits[0].record_start_ms == 1_000
    assert hits[0].record_end_ms == 20_000
    assert hits[0].page_no is None

    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        eigen_hits = await search_hits(app, record_id, "特征值")

    assert [hit.segment_id for hit in eigen_hits] == [eigen_id]


@pytest.mark.anyio
async def test_document_segment_hits_carry_page_no(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        record_id = "22222222-2222-4222-8222-222222222222"
        file_id = "44444444-4444-4444-8444-444444444444"
        segment_id = "55555555-5555-4555-8555-555555555555"
        await seed_record(app, record_id, "讲义导入", capture_type="DOCUMENT_IMPORT")
        await seed_record_file(app, record_id, file_id)
        await seed_document_segment(
            app,
            segment_id=segment_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=0,
            content="第二讲介绍傅里叶级数的收敛判据",
            page_no=3,
        )
        await upsert_index(app, ENTITY_DOCUMENT_SEGMENT, [segment_id])

        hits = await search_hits(app, record_id, "傅里叶")

    assert [hit.segment_id for hit in hits] == [segment_id]
    assert hits[0].entity_type == "document_segment"
    assert hits[0].content == "第二讲介绍傅里叶级数的收敛判据"
    assert hits[0].page_no == 3
    assert hits[0].record_start_ms is None
    assert hits[0].record_end_ms is None


@pytest.mark.anyio
async def test_search_scopes_to_record_and_filters_soft_delete_at_query_time(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        record_a = "22222222-2222-4222-8222-222222222222"
        record_b = "33333333-3333-4333-8333-333333333333"
        transcript_a = "44444444-4444-4444-8444-444444444444"
        file_a = "55555555-5555-4555-8555-555555555555"
        segment_a = "66666666-6666-4666-8666-666666666666"
        segment_b = "77777777-7777-4777-8777-777777777777"
        for record_id in (record_a, record_b):
            await seed_record(app, record_id, "极限专题")
        await seed_record_file(app, record_a, file_a)
        await seed_transcript(app, record_a, transcript_a, "正文")
        await seed_transcript_segment(
            app,
            segment_id=segment_a,
            transcript_id=transcript_a,
            record_id=record_a,
            file_id=file_a,
            sequence_no=0,
            content="极限的夹逼定理是重要工具",
        )
        await seed_transcript_segment(
            app,
            segment_id=segment_b,
            transcript_id=transcript_a,
            record_id=record_b,
            file_id=file_a,
            sequence_no=0,
            content="极限的夹逼定理是重要工具",
        )
        await upsert_index(app, ENTITY_TRANSCRIPT_SEGMENT, [segment_a, segment_b])

        scoped = await search_hits(app, record_a, "极限")
        assert [hit.segment_id for hit in scoped] == [segment_a]

        # 记录软删：查询期回表过滤，索引行不触碰。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET deleted_at = :now "
                    "WHERE id = '33333333-3333-4333-8333-333333333333'"
                ),
                {"now": NOW},
            )
        hidden_record = await search_hits(app, record_b, "极限")
        assert hidden_record == []

        # transcript 软删：同上，查询期过滤。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET deleted_at = NULL "
                    "WHERE id = '33333333-3333-4333-8333-333333333333'"
                )
            )
            await session.execute(
                text("UPDATE transcripts SET deleted_at = :now WHERE id = :transcript_id"),
                {"now": NOW, "transcript_id": transcript_a},
            )
        hidden_transcript = await search_hits(app, record_a, "极限")
        assert hidden_transcript == []

        # 恢复软删即恢复命中：证明索引行全程未被删除。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET deleted_at = NULL WHERE id = :transcript_id"),
                {"transcript_id": transcript_a},
            )
        restored = await search_hits(app, record_a, "极限")

    assert [hit.segment_id for hit in restored] == [segment_a]


@pytest.mark.anyio
async def test_realign_for_edit_syncs_segment_index(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = "22222222-2222-4222-8222-222222222222"
        transcript_id = "33333333-3333-4333-8333-333333333333"
        file_id = "44444444-4444-4444-8444-444444444444"
        kept_id = "55555555-5555-4555-8555-555555555555"
        removed_id = "66666666-6666-4666-8666-666666666666"
        doc_segment_id = "77777777-7777-4777-8777-777777777777"
        await seed_record(app, record_id, "课堂速记")
        await seed_record_file(app, record_id, file_id)
        await seed_transcript(
            app,
            record_id,
            transcript_id,
            "本讲介绍行列式的计算方法\n特征值与特征向量的几何意义",
        )
        await seed_transcript_segment(
            app,
            segment_id=removed_id,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=0,
            content="本讲介绍行列式的计算方法",
        )
        await seed_transcript_segment(
            app,
            segment_id=kept_id,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=1,
            content="特征值与特征向量的几何意义",
        )
        await seed_document_segment(
            app,
            segment_id=doc_segment_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=0,
            content="文档块内容",
        )
        await upsert_index(app, ENTITY_TRANSCRIPT_SEGMENT, [removed_id, kept_id])
        await upsert_index(app, ENTITY_DOCUMENT_SEGMENT, [doc_segment_id])
        assert await index_row_count(app) == 3

        edited = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={
                "content": "特征值与特征向量的几何意义\n新增傅里叶级数一节",
                "expected_source_version": 1,
            },
        )
        assert edited.status_code == 200

        by_removed = await search_hits(app, record_id, "行列式")
        by_kept = await search_hits(app, record_id, "特征值")
        by_new = await search_hits(app, record_id, "傅里叶")
        count = await index_row_count(app)

    assert by_removed == []
    assert [hit.segment_id for hit in by_kept] == [kept_id]
    assert [hit.segment_id for hit in by_new] != []
    assert all(hit.entity_type == "transcript_segment" for hit in by_new)
    # 文档分片随重切清零，索引行同事务清理；转写索引 = 保留句 + 新句。
    assert count == 2


@pytest.mark.anyio
async def test_document_finalize_builds_searchable_segments(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        imported = await client.post(
            "/api/document-imports",
            files={
                "file": (
                    "行列式理论笔记.txt",
                    "本讲系统梳理傅里叶级数的展开方法".encode(),
                    "text/plain",
                )
            },
        )
        assert imported.status_code == 202
        record_id = cast(str, imported.json()["record_id"])
        await wait_for_transcript_ready(client, record_id)

        hits = await search_hits(app, record_id, "傅里叶")

    assert len(hits) == 1
    assert hits[0].entity_type == "document_segment"
    assert hits[0].content == "本讲系统梳理傅里叶级数的展开方法"
    assert hits[0].sequence_no == 0


@pytest.mark.anyio
async def test_backfill_missing_is_idempotent_and_covers_new_segments(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        record_id = "22222222-2222-4222-8222-222222222222"
        transcript_id = "33333333-3333-4333-8333-333333333333"
        file_id = "44444444-4444-4444-8444-444444444444"
        segment_a = "55555555-5555-4555-8555-555555555555"
        segment_b = "66666666-6666-4666-8666-666666666666"
        await seed_record(app, record_id, "线性代数第二讲")
        await seed_record_file(app, record_id, file_id)
        await seed_transcript(app, record_id, transcript_id, "正文")
        await seed_transcript_segment(
            app,
            segment_id=segment_a,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=0,
            content="线性代数研究向量空间与线性映射",
        )
        await seed_transcript_segment(
            app,
            segment_id=segment_b,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=1,
            content="矩阵的秩刻画列空间的维数",
        )

        await SegmentSearchService.backfill_missing(app.state.session_factory)
        first_count = await index_row_count(app)
        assert first_count == 2

        # 重复回填：零副作用。
        await SegmentSearchService.backfill_missing(app.state.session_factory)
        assert await index_row_count(app) == first_count

        # 绕过写路径新增存量分片：回填后可查（不遗漏）。
        segment_c = "77777777-7777-4777-8777-777777777777"
        await seed_transcript_segment(
            app,
            segment_id=segment_c,
            transcript_id=transcript_id,
            record_id=record_id,
            file_id=file_id,
            sequence_no=2,
            content="行列式的几何意义是体积缩放因子",
        )
        await SegmentSearchService.backfill_missing(app.state.session_factory)

        hits = await search_hits(app, record_id, "行列式")

    assert await index_row_count(app) == first_count + 1
    assert [hit.segment_id for hit in hits] == [segment_c]


@pytest.mark.anyio
async def test_search_scope_segments_filters_course_and_soft_delete_with_titles(
    tmp_path: Path,
) -> None:
    """B2 跨记录检索：course 过滤可空、软删照旧过滤、命中携带归属记录标题。"""
    from app.modules.search.schemas import LibrarySegmentSearchHit

    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status, "
                    "created_at, updated_at, deleted_at) "
                    "VALUES (:id, :name, 'INTEREST', 'BEGINNER', 'ACTIVE', :now, :now, NULL)"
                ),
                [
                    {"id": "c-1", "name": "分布式", "now": NOW},
                    {"id": "c-2", "name": "其他课", "now": NOW},
                ],
            )
        record_hash = "88888888-8888-4888-8888-888888888888"
        record_other = "99999999-9999-4999-8999-999999999999"
        record_inbox = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        transcript_hash = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        file_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        await seed_record(app, record_hash, "第 2 讲 一致性哈希", course_id="c-1")
        await seed_record(app, record_other, "独立课记录", course_id="c-2")
        await seed_record(app, record_inbox, "收件箱速记")
        await seed_record_file(app, record_hash, file_id)
        await seed_transcript(app, record_hash, transcript_hash, "正文")
        segments = {
            record_hash: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            record_other: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            record_inbox: "ffffffff-ffff-4fff-8fff-ffffffffffff",
        }
        for record_id, segment_id in segments.items():
            await seed_transcript_segment(
                app,
                segment_id=segment_id,
                transcript_id=transcript_hash,
                record_id=record_id,
                file_id=file_id,
                sequence_no=0,
                content="一致性哈希把节点映射到环上",
            )
        await upsert_index(app, ENTITY_TRANSCRIPT_SEGMENT, list(segments.values()))

        async def scope_hits(course_id: str | None) -> list[LibrarySegmentSearchHit]:
            async with app.state.session_factory() as session:
                return await SegmentSearchService.search_scope_segments(
                    session, course_id, "一致性哈希", 8
                )

        # 全部范围（course_id=None）：跨记录命中并携带标题。
        all_hits = await scope_hits(None)
        assert {hit.record_id for hit in all_hits} == set(segments)
        titles = {hit.record_id: hit.record_title for hit in all_hits}
        assert titles[record_hash] == "第 2 讲 一致性哈希"
        assert titles[record_inbox] == "收件箱速记"
        assert all(hit.content == "一致性哈希把节点映射到环上" for hit in all_hits)

        # 课程过滤：只命中该课程记录。
        course_hits = await scope_hits("c-1")
        assert [hit.record_id for hit in course_hits] == [record_hash]

        # 记录软删：查询期回表过滤。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at = :now WHERE id = :rid"),
                {"now": NOW, "rid": record_hash},
            )
        assert [hit.record_id for hit in await scope_hits("c-1")] == []

        # 无关课程 / 关键词不匹配：零命中。
        assert await scope_hits("c-404") == []
        async with app.state.session_factory() as session:
            empty = await SegmentSearchService.search_scope_segments(session, None, "完全无关词", 8)
        assert empty == []
