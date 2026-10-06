"""资料库 V1 工单 03 测试：统一入库三路 / 判重交互 / WEB_FETCH 闭环 / 幂等。

HTTP 级起完整 app（text/file 真实走 document_worker；web 仅测同步拒绝路径，
不发真实网络）；web 抓取闭环与失败路径走 bare_db + fake adapter 直调
JobRunner.process_one（工单契约：SSRF/抓取/提取全 fake，零真实网络）。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.capture.ingest import LibraryIngestService
from app.modules.capture.web_clip import ClipContent, WebClipError
from app.modules.capture.web_fetch_worker import web_fetch_spec
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import JobRunner
from app.modules.library.backfill import process_chunk
from app.modules.library.models import LibraryItem
from app.modules.library.schemas import LibraryIngestRequest, LibraryIngestSource
from app.shared.events import RecordInvalidationNotifier

TOKEN = "test-launch-token"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"

PAGE_TEXT = "这是一篇用于剪藏闭环测试的中文长文正文。" * 30
FAKE_CLIP = ClipContent(
    text=PAGE_TEXT,
    title="剪藏闭环测试页",
    metadata={"kind": "web", "url": "https://example.com/article"},
)


class _FakeAdapter:
    def __init__(self, clip: ClipContent | None = None, error: WebClipError | None = None) -> None:
        self._clip = clip
        self._error = error

    async def fetch_and_extract(self, url: str) -> ClipContent:
        if self._error is not None:
            raise self._error
        assert self._clip is not None
        return self._clip


class _NoopNotifier(RecordInvalidationNotifier):
    async def notify(self, record_id: str) -> None:
        return None


async def backfill_job_id(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        job_id = (
            await session.execute(
                text("SELECT id FROM processing_jobs WHERE job_type = 'LIBRARY_BACKFILL'")
            )
        ).scalar_one()
    return str(job_id)


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


async def insert_course(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
                "updated_at) VALUES (:id, '剪藏测试课程', 'INTEREST', 'INTERMEDIATE', 'ACTIVE', "
                "'2026-09-19T00:00:00.000000Z', '2026-09-19T00:00:00.000000Z')"
            ).bindparams(id=COURSE_ID)
        )


async def library_item_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str, str]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT id, source_type, content_hash FROM library_items ORDER BY created_at")
            )
        ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


# ---------------------------------------------------------------------------
# HTTP 级：TEXT / FILE / WEB 同步拒绝


@pytest.mark.anyio
async def test_ingest_text_creates_retrievable_item(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _factory):
        response = await client.post(
            "/api/library/ingest",
            json={"source": "text", "title": "手动笔记", "content": "第一行内容\n\n第二行内容"},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["job"] is None
        assert payload["item"]["source_type"] == "TEXT"
        assert payload["item"]["title"] == "手动笔记"
        assert payload["item"]["availability"] == "RETRIEVABLE"

        listed = await client.get("/api/library/items", params={"limit": 10})
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1


@pytest.mark.anyio
async def test_ingest_text_duplicate_conflict_then_allow(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _factory):
        body = {"source": "text", "content": "完全相同的正文内容用于判重测试。"}
        first = await client.post("/api/library/ingest", json=body)
        assert first.status_code == 202
        duplicate = await client.post("/api/library/ingest", json=body)
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "LIBRARY_ITEM_DUPLICATE_CONTENT"
        assert duplicate.json()["params"]["existing_item_id"] == first.json()["item"]["id"]

        kept = await client.post("/api/library/ingest", json={**body, "allow_duplicate": True})
        assert kept.status_code == 202
        assert kept.json()["item"]["id"] != first.json()["item"]["id"]


@pytest.mark.anyio
async def test_ingest_text_rejects_empty_and_oversized(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _factory):
        empty = await client.post("/api/library/ingest", json={"source": "text", "content": "  "})
        assert empty.status_code == 422
        assert empty.json()["code"] == "LIBRARY_INGEST_INVALID_REQUEST"

        oversized = await client.post(
            "/api/library/ingest",
            json={"source": "text", "content": "字" * (1024 * 1024 + 1)},
        )
        assert oversized.status_code == 422
        assert oversized.json()["code"] == "LIBRARY_ITEM_LIMIT_EXCEEDED"


@pytest.mark.anyio
async def test_ingest_web_rejects_invalid_and_blocked_urls(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _factory):
        invalid = await client.post(
            "/api/library/ingest", json={"source": "web", "url": "ftp://example.com/a"}
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "WEB_FETCH_INVALID_URL"

        blocked = await client.post(
            "/api/library/ingest", json={"source": "web", "url": "http://192.168.1.5/admin"}
        )
        assert blocked.status_code == 422
        assert blocked.json()["code"] == "WEB_FETCH_BLOCKED_URL"


@pytest.mark.anyio
async def test_ingest_file_parses_to_retrievable(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client, _factory):
        response = await client.post(
            "/api/library/ingest/file",
            files={
                "file": (
                    "剪藏测试.txt",
                    "文档正文第一段。\n\n文档正文第二段。".encode(),
                    "text/plain",
                )
            },
            data={"allow_duplicate": "false"},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["job"]["job_type"] == "DOCUMENT_PARSE"
        assert payload["item"]["source_type"] == "DOCUMENT"
        assert payload["item"]["availability"] == "PROCESSING"
        item_id = payload["item"]["id"]

        # document_worker 真实解析 → 分片落库 → 条目转可检索（轮询等待终局）
        detail: httpx.Response | None = None
        for _ in range(20):
            detail = await client.get(f"/api/library/items/{item_id}")
            assert detail.status_code == 200
            if detail.json()["availability"] != "PROCESSING":
                break
            await asyncio.sleep(0.3)
        assert detail is not None
        assert detail.json()["availability"] == "RETRIEVABLE"
        assert detail.json()["segment_count"] >= 1
        # 快照进数据目录（全量导出范围），路径在授权 files/ 树内
        data_dir = Path(app.state.data_dir)
        rel = detail.json()["local_path"]
        assert rel is not None and rel.startswith("files/")
        assert (data_dir / rel).is_file()


@pytest.mark.anyio
async def test_ingest_file_duplicate_and_unsupported(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _factory):
        content = b"duplicate file body"
        first = await client.post(
            "/api/library/ingest/file", files={"file": ("a.txt", content, "text/plain")}
        )
        assert first.status_code == 202
        duplicate = await client.post(
            "/api/library/ingest/file", files={"file": ("b.txt", content, "text/plain")}
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "LIBRARY_ITEM_DUPLICATE_CONTENT"
        assert duplicate.json()["params"]["existing_item_id"] == first.json()["item"]["id"]

        bad = await client.post(
            "/api/library/ingest/file",
            files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "DOCUMENT_FORMAT_UNSUPPORTED"


# ---------------------------------------------------------------------------
# 直调：WEB_FETCH 闭环（fake adapter，零真实网络）


@pytest.mark.anyio
async def test_ingest_web_full_loop(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/article"),
        )
        assert accepted.job is not None and accepted.job.job_type.value == "WEB_FETCH"
        assert accepted.item.availability.value == "PROCESSING"
        assert accepted.item.source_type.value == "WEB"
        item_id = accepted.item.id
        job_id = accepted.job.id
        record_id = accepted.job.record_id
        assert record_id is not None

        data_dir = tmp_path / "KnowRealm"
        runner = JobRunner(
            web_fetch_spec(
                session_factory, data_dir, _NoopNotifier(), adapter=_FakeAdapter(FAKE_CLIP)
            ),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True

        async with session_factory() as session:
            job = await session.get(ProcessingJob, job_id)
            item = await session.get(LibraryItem, item_id)
            assert job is not None and item is not None
            assert job.status == "SUCCEEDED"
            assert item.title == "剪藏闭环测试页"
            # hash 恒为 URL 哈希（同 URL 判重锚）；正文哈希记入 metadata
            assert item.content_hash == sha256(b"web:https://example.com/article").hexdigest()
            assert json.loads(item.metadata_json)["content_hash"] != item.content_hash
            assert item.local_path == f"files/{record_id}/{job_id}.md"
            assert item.fetched_at is not None
            assert item.mime_type == "text/markdown"
            assert item.metadata_json and json.loads(item.metadata_json)["url"] == (
                "https://example.com/article"
            )
            snapshot = data_dir / "files" / record_id / f"{job_id}.md"
            assert snapshot.is_file()
            assert snapshot.read_text(encoding="utf-8") == PAGE_TEXT
            rows = (
                await session.execute(
                    text("SELECT status FROM records WHERE id = :rid").bindparams(rid=record_id)
                )
            ).scalar_one()
            assert rows == "NOTE"  # 未归类剪藏：无课程不触发总结
            transcript_n = (
                await session.execute(
                    text("SELECT count(*) FROM transcripts WHERE record_id = :rid").bindparams(
                        rid=record_id
                    )
                )
            ).scalar_one()
            segment = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM document_segments "
                        "WHERE library_item_id = :iid AND record_file_id IS NULL"
                    ).bindparams(iid=item_id)
                )
            ).scalar_one()
            fts = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM segment_search_index ssi "
                        "JOIN document_segments ds ON ds.id = ssi.entity_id "
                        "WHERE ds.library_item_id = :iid"
                    ).bindparams(iid=item_id)
                )
            ).scalar_one()
            record_index = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM search_index "
                        "WHERE entity_type = 'record' AND entity_id = :rid"
                    ).bindparams(rid=record_id)
                )
            ).scalar_one()
        assert transcript_n == 1
        assert segment >= 1
        assert fts >= 1
        assert record_index == 1


@pytest.mark.anyio
async def test_ingest_web_requeued_writeback_overwrites_stale_tmp(tmp_path: Path) -> None:
    """中断重投的写回可安全重入（工单 08 缺口，codex 审查属实）：退出发生在
    临时文件创建后、os.replace 前 → cache/webclips/{job_id}.tmp 残留（该目录
    无启动清理）；重投后 writeback 再写同名临时文件被排他创建拒绝会连续撞
    残留耗尽恢复预算、Job/Record 终态失败。覆盖写后残留被原地覆盖，快照
    落新正文不被半截残留污染。"""
    async with bare_db(tmp_path) as session_factory:
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/article"),
        )
        assert accepted.job is not None
        job_id = accepted.job.id
        record_id = accepted.job.record_id
        assert record_id is not None

        data_dir = tmp_path / "KnowRealm"
        stale_tmp = data_dir / "cache" / "webclips" / f"{job_id}.tmp"
        stale_tmp.parent.mkdir(parents=True, exist_ok=True)
        stale_tmp.write_bytes(b"stale-half-written")

        runner = JobRunner(
            web_fetch_spec(
                session_factory, data_dir, _NoopNotifier(), adapter=_FakeAdapter(FAKE_CLIP)
            ),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True

        async with session_factory() as session:
            job = await session.get(ProcessingJob, job_id)
            assert job is not None and job.status == "SUCCEEDED"
        snapshot = data_dir / "files" / record_id / f"{job_id}.md"
        assert snapshot.read_text(encoding="utf-8") == PAGE_TEXT
        assert not stale_tmp.exists()


@pytest.mark.anyio
async def test_ingest_web_with_course_reaches_summary_pending(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await insert_course(session_factory)
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(
                source=LibraryIngestSource.WEB,
                url="https://example.com/course-article",
                course_id=__import__("uuid").UUID(COURSE_ID),
            ),
        )
        assert accepted.item.course_id == COURSE_ID
        record_id = accepted.job.record_id if accepted.job else None
        assert record_id is not None

        runner = JobRunner(
            web_fetch_spec(
                session_factory,
                tmp_path / "KnowRealm",
                _NoopNotifier(),
                adapter=_FakeAdapter(FAKE_CLIP),
            ),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True
        async with session_factory() as session:
            status = (
                await session.execute(
                    text("SELECT status FROM records WHERE id = :rid").bindparams(rid=record_id)
                )
            ).scalar_one()
        assert status == "SUMMARY_PENDING"


@pytest.mark.anyio
async def test_ingest_web_failure_marks_record_failed(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/paywall"),
        )
        assert accepted.job is not None
        record_id = accepted.job.record_id

        runner = JobRunner(
            web_fetch_spec(
                session_factory,
                tmp_path / "KnowRealm",
                _NoopNotifier(),
                adapter=_FakeAdapter(
                    error=WebClipError("WEB_FETCH_EXTRACT_FAILED", "页面正文过短或为空")
                ),
            ),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True
        async with session_factory() as session:
            job = await session.get(ProcessingJob, accepted.job.id)
            assert job is not None
            assert job.status == "FAILED"
            assert job.error_code == "WEB_FETCH_EXTRACT_FAILED"
            status = (
                await session.execute(
                    text("SELECT status FROM records WHERE id = :rid").bindparams(rid=record_id)
                )
            ).scalar_one()
        assert status == "FAILED"


@pytest.mark.anyio
async def test_ingest_web_duplicate_by_url(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        from app.shared.errors import CodedHTTPException

        body = LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/same")
        first = await LibraryIngestService.ingest_web(session_factory, body)
        with pytest.raises(CodedHTTPException) as exc:
            await LibraryIngestService.ingest_web(session_factory, body)
        assert exc.value.code == "LIBRARY_ITEM_DUPLICATE_CONTENT"
        assert exc.value.params == {"existing_item_id": first.item.id}
        kept = await LibraryIngestService.ingest_web(
            session_factory, body.model_copy(update={"allow_duplicate": True})
        )
        assert kept.item.id != first.item.id


@pytest.mark.anyio
async def test_ingest_text_is_idempotent_with_backfill(tmp_path: Path) -> None:
    """入库自建链接：LIBRARY_BACKFILL 差集扫描不得为同记录再建条目。"""
    from app.modules.library.backfill import ensure_backfill_enqueued

    async with bare_db(tmp_path) as session_factory:
        await LibraryIngestService.ingest_text(
            session_factory,
            tmp_path / "KnowRealm",
            LibraryIngestRequest(
                source=LibraryIngestSource.TEXT, content="幂等验证正文，回填不应重复建条目。"
            ),
        )
        assert len(await library_item_rows(session_factory)) == 1
        async with session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT id FROM processing_jobs WHERE job_type = 'LIBRARY_BACKFILL'")
                )
            ).scalar_one_or_none()
        assert job_row is None  # 入库自建链接，无需回填入队
        # 即便人为触发回填扫描，也不产生第二个条目
        async with session_factory() as session, session.begin():
            await ensure_backfill_enqueued(session)
        job_id = await backfill_job_id(session_factory)
        for _ in range(5):
            if await process_chunk(session_factory, job_id, 200):
                break
        assert len(await library_item_rows(session_factory)) == 1


@pytest.mark.anyio
async def test_ingest_web_item_visible_after_loop(tmp_path: Path) -> None:
    """闭环后条目经 LibraryService 读取为可检索（派生口径端到端）。"""
    async with bare_db(tmp_path) as session_factory:
        accepted = await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(source=LibraryIngestSource.WEB, url="https://example.com/visible"),
        )
        runner = JobRunner(
            web_fetch_spec(
                session_factory,
                tmp_path / "KnowRealm",
                _NoopNotifier(),
                adapter=_FakeAdapter(FAKE_CLIP),
            ),
            session_factory,
            _NoopNotifier(),
        )
        assert await runner.process_one() is True
        from app.modules.library.schemas import LibraryItemListQuery
        from app.modules.library.service import LibraryService

        async with session_factory() as session:
            listed = await LibraryService.list_items(session, LibraryItemListQuery(limit=50))
        target = [i for i in listed.items if i.id == accepted.item.id]
        assert len(target) == 1
        assert target[0].availability.value == "RETRIEVABLE"
