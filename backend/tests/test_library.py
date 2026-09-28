"""资料库 V1 工单 02 测试：迁移升级路径 / 升级前快照 / 幂等回填 / 端点契约 / 提案框架。

回填与可用性派生走 service/worker 直调（不起 lifespan，杜绝 worker 竞态）；
端点契约与 capture 入队钩子起完整 app（worker 真实运行，断言用轮询等待）。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import MIGRATIONS_DIR, run_migrations, supported_user_version
from app.main import create_app
from app.modules.data.archive import ensure_pre_upgrade_snapshot
from app.modules.jobs.runner import RunnerContext
from app.modules.library.backfill import (
    BackfillJobCtx,
    ensure_backfill_enqueued,
    process_chunk,
)
from app.modules.library.backfill import (
    execute as backfill_execute,
)
from app.modules.library.backfill import (
    writeback as backfill_writeback,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import (
    ProposalService,
    clear_appliers,
    register_applier,
    restore_appliers,
)
from app.modules.library.schemas import (
    AgentProposalOut,
    LibraryItemListQuery,
    ProposalListQuery,
    ProposalType,
)
from app.modules.library.service import LibraryService
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"
NOW = "2026-09-19T08:00:00.000000Z"

COURSE_ID = "b0000000-0000-4000-8000-000000000001"
REC_PASTE = "b0000000-0000-4000-8000-000000000011"
REC_QUICK = "b0000000-0000-4000-8000-000000000012"
REC_AUDIO = "b0000000-0000-4000-8000-000000000013"
REC_DOC = "b0000000-0000-4000-8000-000000000014"
REC_MULTI = "b0000000-0000-4000-8000-000000000015"
REC_DELETED = "b0000000-0000-4000-8000-000000000016"
REC_PROCESSING = "b0000000-0000-4000-8000-000000000017"
REC_FAILED = "b0000000-0000-4000-8000-000000000018"
REC_EMPTY = "b0000000-0000-4000-8000-000000000019"
REC_KP = "b0000000-0000-4000-8000-00000000001a"
REC_KP_DEAD_COURSE = "b0000000-0000-4000-8000-00000000001b"
COURSE_DEAD = "b0000000-0000-4000-8000-000000000002"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """只跑迁移 + 建引擎（无 lifespan、无 worker）：service/worker 直调用。"""
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


async def insert(
    sql: str, params: dict[str, object], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession], course_id: str, deleted: bool = False
) -> None:
    await insert(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at, deleted_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', "
        "'ACTIVE', :now, :now, :deleted)",
        {
            "id": course_id,
            "name": "数据库与网络" if course_id == COURSE_ID else "已删课程",
            "now": NOW,
            "deleted": "2026-09-18T00:00:00.000000Z" if deleted else None,
        },
        session_factory,
    )


async def seed_record(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str,
    *,
    capture_type: str = "RECORDING",
    course_id: str | None = COURSE_ID,
    deleted: bool = False,
    title: str = "测试记录",
) -> None:
    await insert(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at, deleted_at) VALUES (:id, :course_id, :capture_type, "
        ":title, 'COMPLETED', 60000, :now, :now, :deleted)",
        {
            "id": record_id,
            "course_id": course_id,
            "capture_type": capture_type,
            "title": title,
            "now": NOW,
            "deleted": "2026-09-18T00:00:00.000000Z" if deleted else None,
        },
        session_factory,
    )


async def seed_file(
    session_factory: async_sessionmaker[AsyncSession],
    file_id: str,
    record_id: str,
    *,
    file_type: str = "AUDIO",
    content_hash: str = "h1",
    sequence_no: int = 0,
    size: int = 10,
) -> None:
    await insert(
        "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
        "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
        "created_at, updated_at, deleted_at) VALUES (:id, :record_id, :file_type, "
        "'RECORDED', :path, :name, :mime, :size, 60000, :seq, :hash, :now, :now, NULL)",
        {
            "id": file_id,
            "record_id": record_id,
            "file_type": file_type,
            "path": f"files/{record_id}/{file_id}.ogg",
            "name": f"{file_id}.ogg",
            "mime": "audio/ogg" if file_type == "AUDIO" else "application/pdf",
            "size": size,
            "seq": sequence_no,
            "hash": content_hash,
            "now": NOW,
        },
        session_factory,
    )


async def seed_transcript(
    session_factory: async_sessionmaker[AsyncSession], record_id: str, content: str
) -> None:
    await insert(
        "INSERT INTO transcripts (id, record_id, language, content, source_version, "
        "edited_by_user, created_at, updated_at, deleted_at) VALUES "
        "(:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)",
        {"id": f"t-{record_id}", "record_id": record_id, "content": content, "now": NOW},
        session_factory,
    )


async def seed_transcript_segment(
    session_factory: async_sessionmaker[AsyncSession], record_id: str
) -> None:
    await insert(
        "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
        "sequence_no, content, content_hash) VALUES (:id, :tid, :record_id, :fid, 0, "
        "'分片正文', 'chash')",
        {
            "id": f"seg-{record_id}",
            "tid": f"t-{record_id}",
            "record_id": record_id,
            "fid": f"f-{record_id}",
        },
        session_factory,
    )


async def seed_document_segment(
    session_factory: async_sessionmaker[AsyncSession], record_id: str
) -> None:
    await insert(
        "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
        "library_item_id, sequence_no, page_no, content, content_hash) VALUES "
        "(:id, :course_id, :record_id, :fid, NULL, 0, 1, '文档分片正文', 'chash')",
        {
            "id": f"dseg-{record_id}",
            "course_id": COURSE_ID,
            "record_id": record_id,
            "fid": f"f-{record_id}",
        },
        session_factory,
    )


async def seed_job(
    session_factory: async_sessionmaker[AsyncSession], record_id: str, job_type: str, status: str
) -> None:
    await insert(
        "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
        "attempts, max_attempts, input_json, created_at, updated_at) VALUES "
        "(:id, :record_id, :job_type, :status, 0, 0, 3, '{}', :now, :now)",
        {
            "id": f"job-{record_id}-{job_type}",
            "record_id": record_id,
            "job_type": job_type,
            "status": status,
            "now": NOW,
        },
        session_factory,
    )


async def run_backfill_once(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """手动走一遍 worker 主链（领取→执行→写回），供无 lifespan 的确定性测试。"""
    async with session_factory() as session, session.begin():
        await ensure_backfill_enqueued(session)
        await session.flush()
        job_id = (
            await session.execute(
                text(
                    "SELECT id FROM processing_jobs WHERE job_type='LIBRARY_BACKFILL' "
                    "AND status='PENDING' ORDER BY created_at LIMIT 1"
                )
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE processing_jobs SET status='RUNNING', started_at=:now WHERE id=:id"),
            {"id": job_id, "now": NOW},
        )
    ctx = BackfillJobCtx(job_id=job_id, record_id="")
    runtime = cast(RunnerContext, None)
    finished = await backfill_execute(ctx, runtime, session_factory)
    assert finished
    await backfill_writeback(ctx, finished, session_factory)


async def seed_full_corpus(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """五类记录 + 软删记录：覆盖 PASTE/QUICK_NOTE/音频/文档/多来源/跳过路径。"""
    await seed_course(session_factory, COURSE_ID)
    await seed_record(session_factory, REC_PASTE, capture_type="PASTE", title="粘贴：费曼学习法")
    await seed_transcript(session_factory, REC_PASTE, "费曼学习法的核心是讲给外行听。")
    await seed_record(
        session_factory, REC_QUICK, capture_type="QUICK_NOTE", course_id=None, title="速记一条"
    )
    await seed_transcript(session_factory, REC_QUICK, "速记正文内容。")
    await seed_record(session_factory, REC_AUDIO, capture_type="RECORDING", title="第3讲 音频")
    await seed_file(session_factory, f"f-{REC_AUDIO}", REC_AUDIO, content_hash="hash-audio")
    await seed_transcript(session_factory, REC_AUDIO, "音频转写正文。")
    await seed_transcript_segment(session_factory, REC_AUDIO)
    await seed_record(session_factory, REC_DOC, capture_type="DOCUMENT_IMPORT", title="讲义.pdf")
    await seed_file(
        session_factory, f"f-{REC_DOC}", REC_DOC, file_type="DOCUMENT", content_hash="hash-doc"
    )
    await seed_document_segment(session_factory, REC_DOC)
    await seed_record(session_factory, REC_MULTI, capture_type="MULTI_SOURCE", title="混合批次")
    await seed_file(
        session_factory, f"f-{REC_MULTI}-1", REC_MULTI, content_hash="m1", sequence_no=0
    )
    await seed_file(
        session_factory,
        f"f-{REC_MULTI}-2",
        REC_MULTI,
        file_type="DOCUMENT",
        content_hash="m2",
        sequence_no=1,
    )
    await seed_record(
        session_factory, REC_DELETED, capture_type="RECORDING", deleted=True, title="已删"
    )
    await seed_file(session_factory, f"f-{REC_DELETED}", REC_DELETED)


# ---------------------------------------------------------------------------
# 迁移与升级前快照


async def apply_migrations_upto(db_path: Path, upto: int) -> None:
    """手工应用 0001..upto（升级路径测试用；复刻 run_migrations 的事务纪律）。"""
    import aiosqlite

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with aiosqlite.connect(db_path) as connection:
        for path in files:
            version = int(path.name[:4])
            if version > upto:
                continue
            sql = path.read_text(encoding="utf-8")
            await connection.executescript(
                f"PRAGMA foreign_keys=OFF;\nBEGIN IMMEDIATE;\n{sql}\n"
                f"PRAGMA user_version={version};\nCOMMIT;"
            )


@pytest.mark.anyio
async def test_migration_upgrade_path_preserves_data(tmp_path: Path) -> None:
    """0025 旧库带数据升级到当前版本（0026→0027 连续两次 chat_sessions 整表重建）：
    数据无损、五档 scope 生效、新列就位。"""
    import aiosqlite

    db_path = tmp_path / "old.db"
    await apply_migrations_upto(db_path, 25)
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute(
            "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
            "updated_at) VALUES ('c1', '课', 'INTEREST', 'INTERMEDIATE', 'ACTIVE', 't', 't')"
        )
        await connection.execute(
            "INSERT INTO chat_sessions (id, mode, scope, created_at, updated_at) "
            "VALUES ('s1', 'ASK', 'COURSE', 't', 't')"
        )
        await connection.execute(
            "INSERT INTO processing_jobs (id, job_type, status, progress, attempts, "
            "max_attempts, input_json, created_at, updated_at) VALUES "
            "('j1', 'SUMMARY', 'SUCCEEDED', 1, 1, 3, '{}', 't', 't')"
        )
        await connection.commit()
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        version_row = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert version_row is not None
        version = cast(int, version_row[0])
        # 迁移版本以发现逻辑为准（新迁移零断言同步：backend/AGENTS.md 迁移纪律）。
        assert version == supported_user_version()
        session_row = await (
            await connection.execute("SELECT count(*) FROM chat_sessions")
        ).fetchone()
        job_row = await (
            await connection.execute("SELECT count(*) FROM processing_jobs")
        ).fetchone()
        assert session_row is not None and job_row is not None
        assert (cast(int, session_row[0]), cast(int, job_row[0])) == (1, 1)
        await connection.execute(
            "INSERT INTO chat_sessions (id, mode, scope, created_at, updated_at) "
            "VALUES ('s2', 'ASK', 'LIBRARY_ITEM', 't', 't')"
        )
        await connection.rollback()
        doc_cols = {
            r[1]
            for r in await (
                await connection.execute("PRAGMA table_info(document_segments)")
            ).fetchall()
        }
        anchor_cols = {
            r[1]
            for r in await (
                await connection.execute("PRAGMA table_info(source_anchors)")
            ).fetchall()
        }
        assert "library_item_id" in doc_cols and "course_material_id" not in doc_cols
        assert "library_item_id" in anchor_cols
        assert "course_id" in anchor_cols  # 可空已由重建保证
        fk = await (await connection.execute("PRAGMA foreign_key_check")).fetchall()
        assert fk == []
        for table in (
            "library_items",
            "library_item_records",
            "agent_proposals",
            "learner_preferences",
        ):
            exists = await (
                await connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t", (table,)
                )
            ).fetchone()
            assert exists is not None, table


@pytest.mark.anyio
async def test_pre_upgrade_snapshot_created_once(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    backups = tmp_path / "backups"
    await apply_migrations_upto(db_path, 25)
    await ensure_pre_upgrade_snapshot(db_path, backups)
    snapshot = backups / f"knowrealm-premigrate-{supported_user_version():04d}.db"
    assert snapshot.exists()
    first = snapshot.read_bytes()
    await ensure_pre_upgrade_snapshot(db_path, backups)  # 已存在不覆盖（保留首次状态）
    assert snapshot.read_bytes() == first
    # 当前版本已达目标：不再快照
    await run_migrations(db_path)
    count = len(list(backups.glob("knowrealm-premigrate-*.db")))
    await ensure_pre_upgrade_snapshot(db_path, backups)
    assert len(list(backups.glob("knowrealm-premigrate-*.db"))) == count
    # 无库文件（全新数据目录）：静默跳过
    await ensure_pre_upgrade_snapshot(tmp_path / "absent.db", backups)


# ---------------------------------------------------------------------------
# 回填 worker


@pytest.mark.anyio
async def test_backfill_creates_and_idempotent(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_corpus(session_factory)
        async with session_factory() as session, session.begin():
            assert await ensure_backfill_enqueued(session) is True
            assert await ensure_backfill_enqueued(session) is False  # 已有活动任务
        await run_backfill_once(session_factory)
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT source_type, count(*) FROM library_items GROUP BY source_type")
                )
            ).all()
            counts = {row[0]: row[1] for row in rows}
            assert counts == {"TEXT": 2, "AUDIO": 2, "DOCUMENT": 2}
            total = (await session.execute(text("SELECT count(*) FROM library_items"))).scalar_one()
            links = (
                await session.execute(text("SELECT count(*) FROM library_item_records"))
            ).scalar_one()
            assert (total, links) == (6, 6)  # 软删记录 0 条目；多来源=2 条目
            paste_item = (
                await session.execute(
                    text(
                        "SELECT content_hash, metadata_json, mime_type, course_id "
                        "FROM library_items WHERE source_type='TEXT' AND title LIKE '粘贴%'"
                    )
                )
            ).one()
            content = "费曼学习法的核心是讲给外行听。"
            assert paste_item[0] == sha256(content.encode("utf-8")).hexdigest()
            source_metadata = json.loads(paste_item[1])
            assert source_metadata["kind"] == "PASTE"
            assert source_metadata["char_count"] == len(content)
            assert paste_item[2] == "text/plain"
            job = (
                await session.execute(
                    text(
                        "SELECT status, result_json FROM processing_jobs "
                        "WHERE job_type='LIBRARY_BACKFILL' ORDER BY created_at DESC LIMIT 1"
                    )
                )
            ).one()
            assert job[0] == "SUCCEEDED"
            assert json.loads(job[1])["created_items"] == 6
        # 幂等重跑：新任务扫描零未链接记录，状态不变
        await run_backfill_once(session_factory)
        async with session_factory() as session:
            total = (await session.execute(text("SELECT count(*) FROM library_items"))).scalar_one()
            assert total == 6


@pytest.mark.anyio
async def test_backfill_resumes_from_cursor(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID)
        for record_id in (REC_PASTE, REC_QUICK, REC_AUDIO):
            await seed_record(
                session_factory, record_id, capture_type="PASTE", title=f"p-{record_id[-2:]}"
            )
            await seed_transcript(session_factory, record_id, f"正文{record_id[-2:]}")
        async with session_factory() as session, session.begin():
            await ensure_backfill_enqueued(session)
            await session.flush()
            job_id = (
                await session.execute(
                    text("SELECT id FROM processing_jobs WHERE job_type='LIBRARY_BACKFILL'")
                )
            ).scalar_one()
            await session.execute(
                text("UPDATE processing_jobs SET status='RUNNING' WHERE id=:id"), {"id": job_id}
            )
        # 逐块推进（chunk=1）：断点续跑可见检查点写入，未完成不置成功
        assert await process_chunk(session_factory, job_id, 1) is False
        async with session_factory() as session:
            raw_state = (
                await session.execute(
                    text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
                )
            ).scalar_one()
            state = json.loads(raw_state)
            assert state["scanned"] == 1 and state["cursor"] > 0
            counted = (
                await session.execute(text("SELECT count(*) FROM library_items"))
            ).scalar_one()
            assert counted == 1
        assert await process_chunk(session_factory, job_id, 200) is True
        async with session_factory() as session:
            counted = (
                await session.execute(text("SELECT count(*) FROM library_items"))
            ).scalar_one()
            assert counted == 3


# ---------------------------------------------------------------------------
# 可用性派生（service 直调）


@pytest.mark.anyio
async def test_availability_derivation(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID)
        await seed_record(session_factory, REC_AUDIO, title="有分片")
        await seed_file(session_factory, f"f-{REC_AUDIO}", REC_AUDIO)
        await seed_transcript(session_factory, REC_AUDIO, "x")
        await seed_transcript_segment(session_factory, REC_AUDIO)
        await seed_record(session_factory, REC_PASTE, capture_type="PASTE", title="纯文本")
        await seed_transcript(session_factory, REC_PASTE, "正文")
        await seed_record(session_factory, REC_PROCESSING, title="处理中")
        await seed_file(session_factory, f"f-{REC_PROCESSING}", REC_PROCESSING)
        await seed_job(session_factory, REC_PROCESSING, "ASR", "PENDING")
        await seed_record(session_factory, REC_FAILED, title="失败")
        await seed_file(session_factory, f"f-{REC_FAILED}", REC_FAILED, file_type="DOCUMENT")
        await seed_job(session_factory, REC_FAILED, "DOCUMENT_PARSE", "FAILED")
        await seed_record(session_factory, REC_EMPTY, title="空")
        await seed_file(session_factory, f"f-{REC_EMPTY}", REC_EMPTY)
        await run_backfill_once(session_factory)
        async with session_factory() as session:
            result = await LibraryService.list_items(session, LibraryItemListQuery())
            availability = {item.title: item.availability.value for item in result.items}
        assert availability["有分片"] == "RETRIEVABLE"
        assert availability["纯文本"] == "RETRIEVABLE"  # TEXT 有正文（子串兜底可检索）
        assert availability["处理中"] == "PROCESSING"
        assert availability["失败"] == "FAILED"
        assert availability["空"] == "EMPTY"


# ---------------------------------------------------------------------------
# 端点契约（完整 app，worker 真实运行）


async def seed_endpoint_corpus(
    session_factory: async_sessionmaker[AsyncSession], client: httpx.AsyncClient
) -> dict[str, str]:
    """直接 SQL 建两个条目（收藏/未归类各一）+ 关联记录 + 知识点，供端点断言。

    seed 前先等启动期回填任务终局：worker 会抢先为尚未手动链接的记录建条目，
    直接 SQL seed 不经 capture 流程（不再入队），此后无竞态。"""
    for _ in range(40):  # 最长 20s：空库回填通常秒级完成
        probe_response = await client.get("/api/library/items", params={"limit": 1})
        probe = probe_response.json()
        backfill_info = cast("dict[str, object] | None", probe.get("backfill"))
        status = cast("str | None", backfill_info.get("status") if backfill_info else None)
        if status not in ("PENDING", "RUNNING"):
            break
        await asyncio.sleep(0.5)
    await seed_course(session_factory, COURSE_ID)
    await seed_course(session_factory, COURSE_DEAD, deleted=True)
    item_ids = {
        "fav": "b0000000-0000-4000-8000-000000000101",
        "review": "b0000000-0000-4000-8000-000000000102",
    }
    await seed_record(session_factory, REC_AUDIO, title="音频来源记录")
    await seed_file(session_factory, f"f-{REC_AUDIO}", REC_AUDIO)
    await seed_transcript(session_factory, REC_AUDIO, "音频转写正文。")
    await seed_transcript_segment(session_factory, REC_AUDIO)
    await seed_record(
        session_factory, REC_QUICK, capture_type="PASTE", course_id=None, title="未归类速记"
    )
    await seed_transcript(session_factory, REC_QUICK, "未归类速记正文。")
    await insert(
        "INSERT INTO library_items (id, course_id, source_type, title, local_path, "
        "mime_type, file_size, content_hash, metadata_json, favorite, status, "
        "created_at, updated_at) VALUES (:id, :course_id, 'AUDIO', :title, :path, "
        "'audio/ogg', 10, :hash, '{}', :favorite, 'ACTIVE', :now, :now)",
        {
            "id": item_ids["fav"],
            "course_id": COURSE_ID,
            "title": "第3讲 音频",
            "path": "files/x.ogg",
            "hash": "h-fav",
            "favorite": 1,
            "now": NOW,
        },
        session_factory,
    )
    await insert(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash, "
        "metadata_json, favorite, status, created_at, updated_at) VALUES "
        "(:id, NULL, 'TEXT', :title, :hash, '{}', 0, 'ACTIVE', :now, :now)",
        {"id": item_ids["review"], "title": "未归类速记", "hash": "h-review", "now": NOW},
        session_factory,
    )
    await insert(
        "INSERT INTO library_item_records (library_item_id, record_id, role, sequence_no, "
        "created_at) VALUES (:item, :record, 'PRIMARY', 0, :now)",
        {"item": item_ids["fav"], "record": REC_AUDIO, "now": NOW},
        session_factory,
    )
    await insert(
        "INSERT INTO library_item_records (library_item_id, record_id, role, sequence_no, "
        "created_at) VALUES (:item, :record, 'PRIMARY', 0, :now)",
        {"item": item_ids["review"], "record": REC_QUICK, "now": NOW},
        session_factory,
    )
    # 知识点：ACTIVE 可见；DRAFT 隐藏；课程软删记录的隐藏
    await seed_record(session_factory, REC_KP, title="有知识点的记录")
    await seed_record(session_factory, REC_KP_DEAD_COURSE, course_id=COURSE_DEAD, title="死课记录")
    for kp_id, record_id, status in (
        ("kp-1", REC_KP, "ACTIVE"),
        ("kp-2", REC_KP, "DRAFT"),
        ("kp-3", REC_KP_DEAD_COURSE, "ACTIVE"),
    ):
        await insert(
            "INSERT INTO knowledge_points (id, record_id, name, detail, tags, importance, "
            "generation_status, created_at, updated_at) VALUES (:id, :record_id, :name, "
            "'细节', '[]', 3, :status, :now, :now)",
            {
                "id": kp_id,
                "record_id": record_id,
                "name": f"知识点{kp_id[-1]}",
                "status": status,
                "now": NOW,
            },
            session_factory,
        )
    return item_ids


@pytest.mark.anyio
async def test_library_endpoints(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client, session_factory):
        item_ids = await seed_endpoint_corpus(session_factory, client)

        listed = await client.get("/api/library/items")
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] == 2
        by_title = {item["title"]: item for item in body["items"]}
        assert by_title["第3讲 音频"]["favorite"] is True
        assert by_title["第3讲 音频"]["course_name"] == "数据库与网络"
        assert by_title["第3讲 音频"]["availability"] == "RETRIEVABLE"
        assert by_title["未归类速记"]["course_id"] is None

        favorites = (await client.get("/api/library/items", params={"view": "favorites"})).json()
        assert [i["title"] for i in favorites["items"]] == ["第3讲 音频"]
        needs = (await client.get("/api/library/items", params={"view": "needs_review"})).json()
        assert [i["title"] for i in needs["items"]] == ["未归类速记"]
        searched = (await client.get("/api/library/items", params={"q": "音频"})).json()
        assert searched["total"] == 1
        # 搜索词中的 %/_ 是字面量而非通配符（escape_like + ESCAPE 子句生效）
        assert (await client.get("/api/library/items", params={"q": "音频%"})).json()["total"] == 0
        assert (await client.get("/api/library/items", params={"q": "第3讲 音_"})).json()[
            "total"
        ] == 0
        typed = (await client.get("/api/library/items", params={"source_type": "TEXT"})).json()
        assert typed["total"] == 1 and typed["items"][0]["source_type"] == "TEXT"
        empty_page = (await client.get("/api/library/items", params={"offset": 10})).json()
        assert empty_page["items"] == [] and empty_page["total"] == 2
        bad_limit = await client.get("/api/library/items", params={"limit": -1})
        assert bad_limit.status_code == 422

        detail = await client.get(f"/api/library/items/{item_ids['fav']}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["segment_count"] == 1
        assert [r["title"] for r in detail_body["derived_records"]] == ["音频来源记录"]

        patched = await client.patch(
            f"/api/library/items/{item_ids['fav']}", json={"favorite": False}
        )
        assert patched.status_code == 200 and patched.json()["favorite"] is False
        empty_patch = await client.patch(f"/api/library/items/{item_ids['fav']}", json={})
        assert empty_patch.status_code == 422
        missing = await client.get("/api/library/items/00000000-0000-4000-8000-00000000dead")
        assert missing.status_code == 404

        content = await client.get(f"/api/library/items/{item_ids['review']}/content")
        assert content.status_code == 200
        assert content.json() == {"content": "未归类速记正文。", "truncated": False}
        truncated = (
            await client.get(
                f"/api/library/items/{item_ids['review']}/content", params={"limit": 3}
            )
        ).json()
        assert truncated == {"content": "未归类", "truncated": True}

        records = (await client.get("/api/library/records")).json()
        record_map = {r["title"]: r for r in records}
        assert record_map["音频来源记录"]["linked_item_count"] == 1
        assert "死课记录" not in record_map  # 课程软删 → 记录不可见
        unclassified = (
            await client.get("/api/library/records", params={"unclassified": True})
        ).json()
        assert {r["title"] for r in unclassified} == {"未归类速记"}

        assets = (await client.get("/api/library/assets")).json()
        assert [a["name"] for a in assets] == ["知识点1"]
        assert assets[0]["record_title"] == "有知识点的记录"


@pytest.mark.anyio
async def test_text_capture_enqueues_backfill(tmp_path: Path) -> None:
    """capture 同事务入队钩子 → worker 真实运行：新粘贴在 /library 可见（e2e）。"""
    async with running_app(tmp_path / "KnowRealm") as (_app, client, _session_factory):
        created = await client.post(
            "/api/text-captures",
            json={
                "capture_type": "PASTE",
                "content": "端到端粘贴：反向传播算法。",
                "course_id": None,
            },
        )
        assert created.status_code == 201
        for _ in range(30):  # worker 轮询 2s，最长等 15s
            await asyncio.sleep(0.5)
            listed = (await client.get("/api/library/items", params={"source_type": "TEXT"})).json()
            if listed["total"] >= 1:
                item = listed["items"][0]
                assert item["source_type"] == "TEXT"
                assert item["availability"] == "RETRIEVABLE"
                content = (await client.get(f"/api/library/items/{item['id']}/content")).json()
                assert content["content"] == "端到端粘贴：反向传播算法。"
                return
        pytest.fail("回填 worker 未在时限内为新粘贴建立资料条目")


# ---------------------------------------------------------------------------
# 提案框架（service 直调 + 路由契约）


async def seed_proposals(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    ids = {
        "pending": "b0000000-0000-4000-8000-000000000201",
        "second": "b0000000-0000-4000-8000-000000000202",
        "rejected": "b0000000-0000-4000-8000-000000000203",
    }
    for key, status in (("pending", "PENDING"), ("second", "PENDING"), ("rejected", "REJECTED")):
        await insert(
            "INSERT INTO agent_proposals (id, proposal_type, status, payload_json, "
            "created_at) VALUES (:id, 'ORGANIZE', :status, '{}', :now)",
            {"id": ids[key], "status": status, "now": NOW},
            session_factory,
        )
    return ids


@pytest.mark.anyio
async def test_proposal_framework_service(tmp_path: Path) -> None:
    """service 直调：每次调用独立会话（service 自持 begin，复用会话会撞已开事务）。"""
    saved_appliers = clear_appliers()
    try:
        async with bare_db(tmp_path) as session_factory:
            ids = await seed_proposals(session_factory)

            async def confirm(proposal_id: str) -> AgentProposalOut:
                async with session_factory() as session:
                    return await ProposalService.confirm(session, proposal_id)

            async def reject(proposal_id: str) -> AgentProposalOut:
                async with session_factory() as session:
                    return await ProposalService.reject(session, proposal_id)

            # 无应用器：确认 → 422 + 提案落 FAILED 诊断
            with pytest.raises(CodedHTTPException) as no_applier:
                await confirm(ids["pending"])
            assert _exc_code(no_applier.value) == "PROPOSAL_APPLY_FAILED"
            async with session_factory() as session:
                rows = (
                    await session.execute(
                        text("SELECT status, error_code FROM agent_proposals WHERE id=:id"),
                        {"id": ids["pending"]},
                    )
                ).one()
            assert rows[0] == "FAILED" and rows[1] == "PROPOSAL_NO_APPLIER"

            # 注册应用器：成功路径 APPLIED；应用器抛错 → FAILED + 部分写入回滚
            applied_marks: list[str] = []

            async def applier(db_session: AsyncSession, proposal: AgentProposal) -> None:
                await db_session.execute(text("UPDATE courses SET name = name WHERE id = 'none'"))
                applied_marks.append(str(proposal.id))

            register_applier(ProposalType.ORGANIZE, applier)
            out = await confirm(ids["second"])
            assert out.status.value == "APPLIED" and applied_marks == [ids["second"]]

            async def bad_applier(db_session: AsyncSession, _proposal: AgentProposal) -> None:
                await db_session.execute(
                    text(
                        "INSERT INTO courses (id, name, learning_context, depth, status, "
                        "created_at, updated_at) VALUES ('x', 'X', 'INTEREST', "
                        "'INTERMEDIATE', 'ACTIVE', 't', 't')"
                    )
                )
                raise CodedHTTPException(
                    code="ORGANIZE_TARGET_MISSING", status_code=409, detail="目标不存在"
                )

            register_applier(ProposalType.ORGANIZE, bad_applier)
            third = "b0000000-0000-4000-8000-000000000204"
            await insert(
                "INSERT INTO agent_proposals (id, proposal_type, status, payload_json, "
                "created_at) VALUES (:id, 'ORGANIZE', 'PENDING', '{}', :now)",
                {"id": third, "now": NOW},
                session_factory,
            )
            with pytest.raises(CodedHTTPException) as failed:
                await confirm(third)
            assert _exc_code(failed.value) == "PROPOSAL_APPLY_FAILED"
            async with session_factory() as session:
                leaked = (
                    await session.execute(text("SELECT count(*) FROM courses WHERE id='x'"))
                ).scalar_one()
                assert leaked == 0  # 应用器部分写入随主事务回滚
                rows = (
                    await session.execute(
                        text("SELECT status, error_code FROM agent_proposals WHERE id=:id"),
                        {"id": third},
                    )
                ).one()
            assert rows[0] == "FAILED" and rows[1] == "ORGANIZE_TARGET_MISSING"

            # 已决提案：确认 409；FAILED 可拒绝；REJECTED 再拒绝 409
            with pytest.raises(CodedHTTPException) as decided:
                await confirm(ids["second"])
            assert _exc_code(decided.value) == "PROPOSAL_ALREADY_DECIDED"
            rejected = await reject(ids["pending"])
            assert rejected.status.value == "REJECTED"
            with pytest.raises(CodedHTTPException) as redecided:
                await reject(ids["rejected"])
            assert _exc_code(redecided.value) == "PROPOSAL_ALREADY_DECIDED"
            async with session_factory() as session:
                listing = await ProposalService.list_proposals(session, ProposalListQuery())
            assert {proposal.status.value for proposal in listing} == {
                "APPLIED",
                "REJECTED",
                "FAILED",
            }
    finally:
        restore_appliers(saved_appliers)


def _exc_code(exc: CodedHTTPException) -> str:
    assert exc.code is not None
    return exc.code


@pytest.mark.anyio
async def test_proposal_routes(tmp_path: Path) -> None:
    saved_appliers = clear_appliers()
    try:
        await _proposal_routes_body(tmp_path)
    finally:
        restore_appliers(saved_appliers)


async def _proposal_routes_body(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client, session_factory):
        ids = await seed_proposals(session_factory)
        listed = await client.get("/api/proposals", params={"status": "PENDING"})
        assert listed.status_code == 200 and len(listed.json()) == 2
        confirm = await client.post(f"/api/proposals/{ids['pending']}/confirm")
        assert confirm.status_code == 422
        assert confirm.json()["code"] == "PROPOSAL_APPLY_FAILED"
        reject = await client.post(f"/api/proposals/{ids['second']}/reject")
        assert reject.status_code == 200 and reject.json()["status"] == "REJECTED"
        assert (await client.post(f"/api/proposals/{ids['second']}/reject")).status_code == 409
        assert (
            await client.post("/api/proposals/00000000-0000-4000-8000-00000000dead/reject")
        ).status_code == 404
