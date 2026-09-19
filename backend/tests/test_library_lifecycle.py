"""资料库 V1 工单 05 测试：生命周期动作 / 回收站 / 重试与 refetch /
索引重建 Worker / AI 整理与提案闭环 / 全量导出恢复。

HTTP 级起完整 app 覆盖生命周期端点契约；worker 与提案应用器走 bare_db
直调（不起 lifespan，杜绝 worker 竞态与真实网络）。routes 导入即注册的
应用器（organize / research_ingest）在直调用例中真实消费。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations, supported_user_version
from app.main import create_app
from app.modules.capture.ingest import LibraryIngestService
from app.modules.jobs.runner import JobRunner
from app.modules.library.index_rebuild_worker import index_rebuild_spec
from app.modules.library.lifecycle import LibraryLifecycleService
from app.modules.library.models import LibraryItem
from app.modules.library.organize import OrganizeService
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import (
    LibraryIngestRequest,
    LibraryIngestSource,
    OrganizeSuggestion,
    OrganizeSuggestionBatch,
    ProposalCreateRequest,
    ProposalType,
)
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

TOKEN = "test-launch-token"
NOW = "2026-09-19T08:00:00.000000Z"
COURSE_ID = "d0000000-0000-4000-8000-000000000001"
COURSE_OTHER = "d0000000-0000-4000-8000-000000000002"


class _NoopNotifier(RecordInvalidationNotifier):
    async def notify(self, record_id: str) -> None:
        return None


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
async def running_app(
    tmp_path: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
    app = create_app(data_dir=tmp_path / "KnowRealm", launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, app.state.session_factory


async def run_sql(
    sql: str, params: dict[str, object], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_course(session_factory: async_sessionmaker[AsyncSession], course_id: str) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)",
        {"id": course_id, "name": f"课程{course_id[-1]}", "now": NOW},
        session_factory,
    )


async def seed_item(
    session_factory: async_sessionmaker[AsyncSession],
    item_id: str,
    *,
    course_id: str | None = COURSE_ID,
    content_hash: str = "h-1",
    title: str = "生命周期条目",
    deleted_at: str | None = None,
    status: str = "ACTIVE",
    origin_uri: str | None = None,
    source_type: str = "TEXT",
    metadata_json: str = "{}",
    local_path: str | None = None,
) -> None:
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, origin_uri, "
        "local_path, content_hash, metadata_json, favorite, status, created_at, "
        "updated_at, deleted_at) VALUES (:id, :course_id, :source_type, :title, "
        ":origin_uri, :local_path, :hash, :metadata, 0, :status, :now, :now, :deleted)",
        {
            "id": item_id,
            "course_id": course_id,
            "source_type": source_type,
            "title": title,
            "origin_uri": origin_uri,
            "local_path": local_path,
            "hash": content_hash,
            "metadata": metadata_json,
            "status": status,
            "now": NOW,
            "deleted": deleted_at,
        },
        session_factory,
    )


async def seed_record(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str,
    *,
    course_id: str | None = COURSE_ID,
    deleted_at: str | None = None,
    status: str = "COMPLETED",
) -> None:
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at, deleted_at) VALUES (:id, :course_id, 'PASTE', :title, "
        ":status, 0, :now, :now, :deleted)",
        {
            "id": record_id,
            "course_id": course_id,
            "title": f"记录{record_id[-2:]}",
            "status": status,
            "now": NOW,
            "deleted": deleted_at,
        },
        session_factory,
    )


async def link_item_record(
    session_factory: async_sessionmaker[AsyncSession], item_id: str, record_id: str
) -> None:
    await run_sql(
        "INSERT INTO library_item_records (library_item_id, record_id, role, sequence_no, "
        "created_at) VALUES (:item, :record, 'PRIMARY', 0, :now)",
        {"item": item_id, "record": record_id, "now": NOW},
        session_factory,
    )


# ---------------------------------------------------------------------------
# 端点契约（完整 app）


@pytest.mark.anyio
async def test_lifecycle_endpoints(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client, session_factory):
        # 等启动期回填终局，避免 worker 与手工 seed 竞态
        for _ in range(40):
            probe = (await client.get("/api/library/items", params={"limit": 1})).json()
            backfill = probe.get("backfill")
            if not backfill or backfill.get("status") not in ("PENDING", "RUNNING"):
                break
            await asyncio.sleep(0.5)
        assert app.state.session_factory is session_factory
        await seed_course(session_factory, COURSE_ID)
        await seed_course(session_factory, COURSE_OTHER)
        item_id = "d0000000-0000-4000-8000-000000000101"
        record_id = "d0000000-0000-4000-8000-000000000111"
        await seed_item(session_factory, item_id)
        await seed_record(session_factory, record_id)
        await link_item_record(session_factory, item_id, record_id)

        # 重命名 / 归类 / 取消归类 / 收藏
        renamed = await client.patch(f"/api/library/items/{item_id}", json={"title": "新标题"})
        assert renamed.status_code == 200 and renamed.json()["title"] == "新标题"
        moved = await client.patch(
            f"/api/library/items/{item_id}", json={"course_id": COURSE_OTHER}
        )
        assert moved.status_code == 200 and moved.json()["course_id"] == COURSE_OTHER
        # 派生 Record 不随条目归类静默移动（课程仍是原课程）
        async with session_factory() as session:
            record_course = (
                await session.execute(
                    text("SELECT course_id FROM records WHERE id=:r"), {"r": record_id}
                )
            ).scalar_one()
        assert record_course == COURSE_ID
        unclassified = await client.patch(f"/api/library/items/{item_id}", json={"course_id": None})
        assert unclassified.status_code == 200 and unclassified.json()["course_id"] is None
        bad_course = await client.patch(
            f"/api/library/items/{item_id}",
            json={"course_id": "00000000-0000-4000-8000-00000000dead"},
        )
        assert bad_course.status_code == 404
        assert bad_course.json()["code"] == "COURSE_NOT_FOUND"
        empty_title = await client.patch(f"/api/library/items/{item_id}", json={"title": "  "})
        assert empty_title.status_code == 422
        assert empty_title.json()["code"] == "LIBRARY_PATCH_EMPTY"

        # 归档 / 恢复：默认视图退出、归档视图可见、重复归档 409
        archived = await client.post(f"/api/library/items/{item_id}/archive")
        assert archived.status_code == 200 and archived.json()["status"] == "ARCHIVED"
        default_list = (await client.get("/api/library/items")).json()
        assert all(item["id"] != item_id for item in default_list["items"])
        archived_list = (await client.get("/api/library/items", params={"view": "archived"})).json()
        assert [item["id"] for item in archived_list["items"]] == [item_id]
        re_archive = await client.post(f"/api/library/items/{item_id}/archive")
        assert re_archive.status_code == 409
        assert re_archive.json()["code"] == "LIBRARY_ITEM_ALREADY_ARCHIVED"
        unarchived = await client.post(f"/api/library/items/{item_id}/unarchive")
        assert unarchived.status_code == 200 and unarchived.json()["status"] == "ACTIVE"
        re_unarchive = await client.post(f"/api/library/items/{item_id}/unarchive")
        assert re_unarchive.status_code == 409
        assert re_unarchive.json()["code"] == "LIBRARY_ITEM_ALREADY_ACTIVE"

        # 软删 → 默认/归档视图消失、回收站视图可见（含 deleted_at）
        deleted = await client.delete(f"/api/library/items/{item_id}")
        assert deleted.status_code == 200 and deleted.json()["deleted_at"] is not None
        trash = (await client.get("/api/library/items", params={"view": "trash"})).json()
        assert [item["id"] for item in trash["items"]] == [item_id]
        assert trash["items"][0]["deleted_at"] is not None
        archived_after_delete = (
            await client.get("/api/library/items", params={"view": "archived"})
        ).json()
        assert archived_after_delete["items"] == []

        # 软删零级联：派生 Record 原样保留
        async with session_factory() as session:
            record_alive = (
                await session.execute(
                    text("SELECT deleted_at FROM records WHERE id=:r"), {"r": record_id}
                )
            ).scalar_one()
        assert record_alive is None

        # 恢复：非回收站条目 409；回收站条目恢复后回到默认视图
        live_item = "d0000000-0000-4000-8000-000000000102"
        await seed_item(session_factory, live_item)
        restore_alive = await client.post(f"/api/library/items/{live_item}/restore")
        assert restore_alive.status_code == 409
        assert restore_alive.json()["code"] == "LIBRARY_ITEM_NOT_IN_TRASH"
        restored = await client.post(f"/api/library/items/{item_id}/restore")
        assert restored.status_code == 200 and restored.json()["deleted_at"] is None
        default_after = (await client.get("/api/library/items")).json()
        assert any(item["id"] == item_id for item in default_after["items"])
        trash_after = (await client.get("/api/library/items", params={"view": "trash"})).json()
        assert trash_after["items"] == []

        # 物理删除防线：存在未软删派生 Record 时 409
        permanent_blocked = await client.delete(
            f"/api/library/items/{item_id}", params={"permanent": True}
        )
        assert permanent_blocked.status_code == 409
        assert permanent_blocked.json()["code"] == "LIBRARY_ITEM_HAS_DERIVED_RECORDS"
        missing = await client.delete("/api/library/items/00000000-0000-4000-8000-00000000dead")
        assert missing.status_code == 404


# ---------------------------------------------------------------------------
# 物理删除与回收站保留期（service 直调）


@pytest.mark.anyio
async def test_permanent_delete_and_retention(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        item_expired = "d0000000-0000-4000-8000-000000000201"
        item_fresh = "d0000000-0000-4000-8000-000000000202"
        record_guard = "d0000000-0000-4000-8000-000000000211"
        await seed_item(
            session_factory,
            item_expired,
            course_id=None,
            deleted_at="2026-09-01T00:00:00.000000Z",
        )
        await seed_item(
            session_factory,
            item_fresh,
            course_id=None,
            content_hash="h-2",
            deleted_at="2026-10-01T00:00:00.000000Z",
        )
        await seed_record(session_factory, record_guard, course_id=None)
        await link_item_record(session_factory, item_expired, record_guard)

        # 有存活派生 Record：即使保留期届满也不清理
        now = datetime(2026, 10, 15, tzinfo=UTC)
        await LibraryLifecycleService.purge_expired_trash(session_factory, now=now)
        async with session_factory() as session:
            remaining = (
                await session.execute(text("SELECT count(*) FROM library_items"))
            ).scalar_one()
        assert remaining == 2

        # 派生 Record 软删后：届满条目被物理清理；29 天内条目保留；Record 不动
        await run_sql(
            "UPDATE records SET deleted_at='2026-09-10T00:00:00.000000Z' WHERE id=:id",
            {"id": record_guard},
            session_factory,
        )
        await LibraryLifecycleService.purge_expired_trash(session_factory, now=now)
        async with session_factory() as session:
            expired_gone = await session.get(LibraryItem, item_expired)
            fresh_kept = await session.get(LibraryItem, item_fresh)
            record_kept = (
                await session.execute(
                    text("SELECT deleted_at FROM records WHERE id=:r"), {"r": record_guard}
                )
            ).scalar_one()
            links = (
                await session.execute(text("SELECT count(*) FROM library_item_records"))
            ).scalar_one()
        assert expired_gone is None
        assert fresh_kept is not None
        assert record_kept is not None  # 物理清理不动 Record
        assert links == 0  # 届满条目的链接随 CASCADE 消亡


@pytest.mark.anyio
async def test_restore_rebuilds_missing_index_and_verifies_snapshot(tmp_path: Path) -> None:
    """回收站恢复：索引缺失幂等重建 + 快照哈希校验失败拒绝恢复。"""
    async with bare_db(tmp_path) as session_factory:
        data_dir = tmp_path / "KnowRealm"
        item_id = "d0000000-0000-4000-8000-000000000221"
        record_id = "d0000000-0000-4000-8000-000000000231"
        snapshot_rel = f"files/{record_id}/snap.md"
        snapshot_path = data_dir / "files" / record_id / "snap.md"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(b"snapshot-bytes")
        await seed_item(
            session_factory,
            item_id,
            course_id=None,
            source_type="WEB",
            deleted_at="2026-09-18T00:00:00.000000Z",
            origin_uri="https://example.com/snap",
            local_path=snapshot_rel,
            metadata_json=json.dumps(
                {
                    "kind": "web",
                    "content_hash": sha256(b"snapshot-bytes").hexdigest(),
                }
            ),
        )
        await seed_record(session_factory, record_id, course_id=None)
        await link_item_record(session_factory, item_id, record_id)
        file_id = f"f-{record_id}"
        await run_sql(
            "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
            "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
            "created_at, updated_at, deleted_at) VALUES (:id, :record_id, 'AUDIO', 'RECORDED', "
            ":path, :name, 'audio/ogg', 10, 0, 0, 'ch', :now, :now, NULL)",
            {
                "id": file_id,
                "record_id": record_id,
                "path": f"files/{record_id}/{file_id}.ogg",
                "name": f"{file_id}.ogg",
                "now": NOW,
            },
            session_factory,
        )
        await run_sql(
            "INSERT INTO transcripts (id, record_id, language, content, source_version, "
            "edited_by_user, created_at, updated_at) VALUES ('t2', :rid, 'zh-CN', "
            "'恢复重建索引正文', 1, 0, :now, :now)",
            {"rid": record_id, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
            "sequence_no, content, content_hash) VALUES ('s2', 't2', :rid, :fid, 0, "
            "'恢复重建索引正文', 'ch2')",
            {"rid": record_id, "fid": file_id},
            session_factory,
        )
        # 模拟软删期间索引意外丢失
        await run_sql("DELETE FROM segment_search_index", {}, session_factory)
        await run_sql("DELETE FROM search_index", {}, session_factory)

        # 快照被篡改：恢复被拒（LIBRARY_ITEM_SNAPSHOT_INVALID）
        snapshot_path.write_bytes(b"tampered")
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as corrupt:
                await LibraryLifecycleService.restore(session_factory, data_dir, item_id)
        assert corrupt.value.code == "LIBRARY_ITEM_SNAPSHOT_INVALID"
        async with session_factory() as session:
            still_trashed = (
                await session.execute(
                    text("SELECT deleted_at FROM library_items WHERE id=:id"),
                    {"id": item_id},
                )
            ).scalar_one()
        assert still_trashed is not None

        # 快照还原后恢复成功：索引行随之重建（可检索性恢复）
        snapshot_path.write_bytes(b"snapshot-bytes")
        async with session_factory() as session:
            restored = await LibraryLifecycleService.restore(session_factory, data_dir, item_id)
        assert restored.deleted_at is None
        async with session_factory() as session:
            seg_rows = (
                await session.execute(text("SELECT count(*) FROM segment_search_index"))
            ).scalar_one()
            nav_rows = (
                await session.execute(text("SELECT count(*) FROM search_index"))
            ).scalar_one()
        assert seg_rows >= 1 and nav_rows >= 1


# ---------------------------------------------------------------------------
# 失败重试 / refetch / 索引重建


@pytest.mark.anyio
async def test_retry_refetch_rebuild(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/a"),
        )
        item_id = accepted.item.id
        assert accepted.job is not None
        job_id = accepted.job.id
        record_id = accepted.job.record_id
        assert record_id is not None

        # 无 FAILED 任务：重试 422
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as no_failed:
                await LibraryLifecycleService.retry_failed(session, item_id)
        assert no_failed.value.code == "LIBRARY_RETRY_NOT_APPLICABLE"

        # 种失败终态：job FAILED + Record FAILED
        await run_sql(
            "UPDATE processing_jobs SET status='FAILED', error_code='WEB_FETCH_UNREACHABLE', "
            "attempts=1, updated_at=:now WHERE id=:id",
            {"id": job_id, "now": NOW},
            session_factory,
        )
        await run_sql(
            "UPDATE records SET status='FAILED' WHERE id=:rid",
            {"rid": record_id},
            session_factory,
        )
        async with session_factory() as session:
            retried = await LibraryLifecycleService.retry_failed(session, item_id)
        assert retried.availability.value == "PROCESSING"
        async with session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, attempts, error_code FROM processing_jobs WHERE id=:id"),
                    {"id": job_id},
                )
            ).one()
            record_status = (
                await session.execute(
                    text("SELECT status FROM records WHERE id=:rid"), {"rid": record_id}
                )
            ).scalar_one()
        assert job_row[0] == "PENDING" and job_row[1] == 0
        assert job_row[2] is None
        assert record_status == "CONTENT_PROCESSING"

        # refetch：同 URL 新条目（不覆盖旧快照、判重锚放行）
        refetched = await LibraryLifecycleService.refetch(session_factory, item_id)
        assert refetched.item.id != item_id
        assert refetched.item.origin_uri == "https://example.com/a"
        async with session_factory() as session:
            total = (await session.execute(text("SELECT count(*) FROM library_items"))).scalar_one()
            old_item = await session.get(LibraryItem, item_id)
        assert total == 2
        assert old_item is not None  # 旧条目原样保留

        # 非 WEB 条目 refetch 422
        text_item = "d0000000-0000-4000-8000-000000000301"
        await seed_item(session_factory, text_item, course_id=None, source_type="TEXT")
        with pytest.raises(CodedHTTPException) as unsupported:
            await LibraryLifecycleService.refetch(session_factory, text_item)
        assert unsupported.value.code == "LIBRARY_REFETCH_UNSUPPORTED"


@pytest.mark.anyio
async def test_index_rebuild_worker_restores_missing_rows(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        item_id = "d0000000-0000-4000-8000-000000000401"
        record_id = "d0000000-0000-4000-8000-000000000411"
        await seed_item(session_factory, item_id, course_id=None)
        await seed_record(session_factory, record_id, course_id=None)
        await link_item_record(session_factory, item_id, record_id)
        file_id = f"f-{record_id}"
        await run_sql(
            "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
            "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
            "created_at, updated_at, deleted_at) VALUES (:id, :record_id, 'AUDIO', 'RECORDED', "
            ":path, :name, 'audio/ogg', 10, 0, 0, 'ch', :now, :now, NULL)",
            {
                "id": file_id,
                "record_id": record_id,
                "path": f"files/{record_id}/{file_id}.ogg",
                "name": f"{file_id}.ogg",
                "now": NOW,
            },
            session_factory,
        )
        await run_sql(
            "INSERT INTO transcripts (id, record_id, language, content, source_version, "
            "edited_by_user, created_at, updated_at) VALUES ('t1', :rid, 'zh-CN', "
            "'重建索引测试正文', 1, 0, :now, :now)",
            {"rid": record_id, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
            "sequence_no, content, content_hash) VALUES ('s1', 't1', :rid, :fid, 0, "
            "'重建索引测试正文', 'ch')",
            {"rid": record_id, "fid": file_id},
            session_factory,
        )
        # 模拟索引意外丢失
        await run_sql("DELETE FROM segment_search_index", {}, session_factory)
        await run_sql("DELETE FROM search_index", {}, session_factory)

        job = await LibraryLifecycleService.enqueue_index_rebuild(session_factory, item_id)
        runner = JobRunner(
            index_rebuild_spec(session_factory, _NoopNotifier()),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True
        async with session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, result_json FROM processing_jobs WHERE id=:id"),
                    {"id": job.id},
                )
            ).one()
            seg_rows = (
                await session.execute(text("SELECT count(*) FROM segment_search_index"))
            ).scalar_one()
            nav_rows = (
                await session.execute(text("SELECT count(*) FROM search_index"))
            ).scalar_one()
        assert job_row[0] == "SUCCEEDED"
        assert json.loads(job_row[1])["rebuilt_records"] == 1
        assert seg_rows >= 1 and nav_rows >= 1


# ---------------------------------------------------------------------------
# AI 整理与提案闭环（bare_db 直调）


@pytest.mark.anyio
async def test_organize_scan_detects_duplicates(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID)
        await seed_item(session_factory, "d0000000-0000-4000-8000-000000000501", content_hash="dup")
        await seed_item(
            session_factory,
            "d0000000-0000-4000-8000-000000000502",
            content_hash="dup",
            course_id=None,
            title="未归类重复",
        )
        await seed_item(
            session_factory,
            "d0000000-0000-4000-8000-000000000503",
            content_hash="solo",
            title="独一份",
        )
        async with session_factory() as session:
            scan = await OrganizeService.scan(session)
        assert len(scan.duplicates) == 1
        assert {item.id for item in scan.duplicates[0].items} == {
            "d0000000-0000-4000-8000-000000000501",
            "d0000000-0000-4000-8000-000000000502",
        }
        assert [item.id for item in scan.unclassified] == ["d0000000-0000-4000-8000-000000000502"]


@pytest.mark.anyio
async def test_organize_propose_confirm_reject(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID)
        item_id = "d0000000-0000-4000-8000-000000000601"
        await seed_item(session_factory, item_id, course_id=None, title="  乱码标题.pdf  ")

        async def fake_generate(prompt: str) -> OrganizeSuggestionBatch:
            assert item_id in prompt
            return OrganizeSuggestionBatch(
                suggestions=[
                    OrganizeSuggestion(item_id=item_id, title="规范标题", course_id=COURSE_ID),
                    # 幻觉条目：跳过；幻觉课程：降级为仅标题建议
                    OrganizeSuggestion(item_id="not-exist", title="x"),
                    OrganizeSuggestion(
                        item_id=item_id,
                        title="二次",
                        course_id="00000000-0000-4000-8000-00000000dead",
                    ),
                ]
            )

        proposed = await OrganizeService.propose(session_factory, fake_generate)
        assert proposed.skipped == ["not-exist"]
        assert len(proposed.created) == 2

        # 未确认零事实变更
        async with session_factory() as session:
            untouched = await session.get(LibraryItem, item_id)
        assert untouched is not None and untouched.title == "  乱码标题.pdf  "

        # 确认带课程的建议：标题 + 归类原子应用
        first = next(p for p in proposed.created if p.payload.get("course_id") == COURSE_ID)
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, first.id)
        assert confirmed.status.value == "APPLIED"
        async with session_factory() as session:
            applied = await session.get(LibraryItem, item_id)
        assert applied is not None
        assert applied.title == "规范标题"
        assert applied.course_id == COURSE_ID

        # 拒绝另一条：零事实变更
        second = next(p for p in proposed.created if p.payload.get("course_id") is None)
        async with session_factory() as session:
            rejected = await ProposalService.reject(session, second.id)
        assert rejected.status.value == "REJECTED"
        async with session_factory() as session:
            still = await session.get(LibraryItem, item_id)
        assert still is not None and still.title == "规范标题"


@pytest.mark.anyio
async def test_organize_apply_failure_marks_proposal_failed(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        proposal_id = "d0000000-0000-4000-8000-000000000651"
        await run_sql(
            "INSERT INTO agent_proposals (id, proposal_type, status, target_type, target_id, "
            "payload_json, created_at) VALUES (:id, 'ORGANIZE', 'PENDING', 'library_item', "
            ":target, :payload, :now)",
            {
                "id": proposal_id,
                "target": "d0000000-0000-4000-8000-000000000652",
                "payload": json.dumps(
                    {"item_id": "d0000000-0000-4000-8000-000000000652", "title": "新名"}
                ),
                "now": NOW,
            },
            session_factory,
        )
        # 目标条目不存在：确认失败落 FAILED + 稳定错误码（可重试路径）
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as failed:
                await ProposalService.confirm(session, proposal_id)
        assert failed.value.code == "PROPOSAL_APPLY_FAILED"
        async with session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT status, error_code FROM agent_proposals WHERE id=:id"),
                    {"id": proposal_id},
                )
            ).one()
        assert row[0] == "FAILED" and row[1] == "LIBRARY_ITEM_NOT_FOUND"


@pytest.mark.anyio
async def test_research_ingest_proposal_roundtrip(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        # 通用创建：坏 payload 判别拒绝
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as bad:
                await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.RESEARCH_INGEST,
                        payload={"url": "not a url"},
                    ),
                )
        assert bad.value.code == "PROPOSAL_PAYLOAD_INVALID"

        # 正常创建 → PENDING（未确认零事实变更）
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.RESEARCH_INGEST,
                    payload={"url": "https://example.com/research", "title": "研究来源"},
                ),
            )
        assert proposal.status.value == "PENDING"
        async with session_factory() as session:
            items_before = (
                await session.execute(text("SELECT count(*) FROM library_items"))
            ).scalar_one()
        assert items_before == 0

        # 确认 → 业务入库：条目 + WEB_FETCH 任务建立（未抓取、零分片）
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal.id)
        assert confirmed.status.value == "APPLIED"
        async with session_factory() as session:
            item_row = (
                await session.execute(text("SELECT origin_uri FROM library_items"))
            ).scalar_one()
            fetch_jobs = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM processing_jobs WHERE job_type='WEB_FETCH' "
                        "AND status='PENDING'"
                    )
                )
            ).scalar_one()
            segments = (
                await session.execute(text("SELECT count(*) FROM document_segments"))
            ).scalar_one()
        assert item_row == "https://example.com/research"
        assert fetch_jobs == 1
        assert segments == 0  # 未成功抓取前不进 RAG

        # 同 URL 再提案再确认 → 判重失败落 FAILED + 稳定错误码
        async with session_factory() as session:
            duplicate_proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.RESEARCH_INGEST,
                    payload={"url": "https://example.com/research", "title": "重复来源"},
                ),
            )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as failed:
                await ProposalService.confirm(session, duplicate_proposal.id)
        assert failed.value.code == "PROPOSAL_APPLY_FAILED"
        assert failed.value.params == {"errorCode": "LIBRARY_ITEM_DUPLICATE_CONTENT"}
        async with session_factory() as session:
            failed_row = (
                await session.execute(
                    text("SELECT status, error_code FROM agent_proposals WHERE id=:id"),
                    {"id": duplicate_proposal.id},
                )
            ).one()
        assert failed_row[0] == "FAILED"
        assert failed_row[1] == "LIBRARY_ITEM_DUPLICATE_CONTENT"


# ---------------------------------------------------------------------------
# 全量导出 → 空库恢复（资料条目 / 关联 / 快照）


@pytest.mark.anyio
async def test_export_restore_keeps_library(tmp_path: Path) -> None:
    from app.modules.data.archive import export_archive, restore_archive

    source = tmp_path / "source"
    source.mkdir()
    db_path = source / "knowrealm.db"
    await run_migrations(db_path)
    (source / "cache").mkdir(exist_ok=True)  # VACUUM INTO 快照目标目录
    _engine, session_factory = create_database(db_path)
    try:
        item_id = "d0000000-0000-4000-8000-000000000701"
        record_id = "d0000000-0000-4000-8000-000000000711"
        snapshot_rel = f"files/{record_id}/snap.md"
        snapshot_abs = source / "files" / record_id / "snap.md"
        snapshot_abs.parent.mkdir(parents=True, exist_ok=True)
        snapshot_abs.write_text("快照正文", encoding="utf-8")
        await seed_course(session_factory, COURSE_ID)
        await seed_item(
            session_factory,
            item_id,
            source_type="WEB",
            origin_uri="https://example.com/snap",
            local_path=snapshot_rel,
            metadata_json=json.dumps({"kind": "web", "content_hash": sha256(b"x").hexdigest()}),
        )
        await seed_record(session_factory, record_id)
        await link_item_record(session_factory, item_id, record_id)
    finally:
        await _engine.dispose()
    file_name = await export_archive(source, include_secrets=False)

    target = tmp_path / "target"
    target.mkdir()
    await restore_archive(target, source / "exports" / file_name)
    assert (target / snapshot_rel).read_text(encoding="utf-8") == "快照正文"
    async with aiosqlite.connect(target / "knowrealm.db") as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert cast(int, version[0]) == supported_user_version()
        item_count = await (
            await connection.execute("SELECT count(*) FROM library_items")
        ).fetchone()
        link_count = await (
            await connection.execute("SELECT count(*) FROM library_item_records")
        ).fetchone()
        uri = await (await connection.execute("SELECT origin_uri FROM library_items")).fetchone()
    assert item_count[0] == 1 and link_count[0] == 1
    assert uri[0] == "https://example.com/snap"
