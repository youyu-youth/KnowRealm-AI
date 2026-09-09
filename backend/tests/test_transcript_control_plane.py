import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"


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


async def seed_transcript_record(app: FastAPI, *, status: str = "SUMMARY_READY") -> str:
    record_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, NULL, 'AUDIO_IMPORT', '音频', :status, 1000, NULL, :now, :now, NULL)"
            ),
            {"id": record_id, "status": status, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts "
                "(id, record_id, language, content, source_version, edited_by_user, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', '旧正文', 1, 0, :now, :now, NULL)"
            ),
            {"id": str(uuid4()), "record_id": record_id, "now": now},
        )
    return record_id


@pytest.mark.anyio
async def test_transcript_patch_is_atomic_and_supersedes_existing_summary(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app)
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO ai_summaries "
                    "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                    "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                    "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 1, 1, '主题', '摘要', '{}', 'CONFIRMED', "
                    "'model', 'v1', '{}', 1, NULL, :now, :now, :now, NULL)"
                ),
                {"id": str(uuid4()), "record_id": record_id, "now": now},
            )

        before = app.state.record_notifier.version(record_id)
        updated = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "修正后的正文", "expected_source_version": 1},
        )
        stale = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "静默覆盖", "expected_source_version": 1},
        )
        after = app.state.record_notifier.version(record_id)

        async with app.state.session_factory() as session:
            state = (
                await session.execute(
                    text(
                        "SELECT r.status, t.content, t.source_version, t.edited_by_user, "
                        "s.status, (SELECT count(*) FROM processing_jobs WHERE record_id=:id) "
                        "FROM records r JOIN transcripts t ON t.record_id=r.id "
                        "JOIN ai_summaries s ON s.record_id=r.id WHERE r.id=:id"
                    ),
                    {"id": record_id},
                )
            ).one()

    assert updated.status_code == 200
    assert updated.json()["source_version"] == 2
    assert stale.status_code == 409
    assert tuple(state) == ("SUMMARY_PENDING", "修正后的正文", 2, 1, "SUPERSEDED", 0)
    assert before != after


@pytest.mark.anyio
async def test_summary_processing_blocks_transcript_edit(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app, status="SUMMARY_PROCESSING")
        response = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "不能写入", "expected_source_version": 1},
        )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_manual_asr_retry_reuses_job_and_preserves_checkpoint(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app, status="FAILED")
        job_id = str(uuid4())
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        checkpoint = {
            "cursor": 1,
            "chunks": [
                {"index": 0, "status": "SUCCEEDED", "task_id": "11"},
                {"index": 1, "status": "FAILED", "task_id": "12"},
            ],
        }
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO processing_jobs "
                    "(id, record_id, job_type, status, progress, attempts, max_attempts, "
                    "next_run_at, waiting_reason, input_json, result_json, error_code, "
                    "error_message, started_at, finished_at, created_at, updated_at) "
                    "VALUES (:id, :record_id, 'ASR', 'FAILED', 0.5, 3, 3, NULL, NULL, '{}', "
                    ":result, 'ASR_RECOGNITION_FAILED', '失败', :now, :now, :now, :now)"
                ),
                {
                    "id": job_id,
                    "record_id": record_id,
                    "result": json.dumps(checkpoint),
                    "now": now,
                },
            )

        response = await client.post(
            f"/api/processing-jobs/{job_id}/retries",
            json={"record_id": record_id},
        )
        async with app.state.session_factory() as session:
            raw = (
                await session.execute(
                    text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
                )
            ).scalar_one()

    assert response.status_code == 202
    assert response.json()["id"] == job_id
    assert response.json()["status"] == "PENDING"
    assert response.json()["attempts"] == 0
    restored = cast(dict[str, object], json.loads(cast(str, raw)))
    chunks = cast(list[dict[str, object]], restored["chunks"])
    assert chunks[0] == {"index": 0, "status": "SUCCEEDED", "task_id": "11"}
    assert chunks[1] == {"index": 1, "status": "PENDING"}


@pytest.mark.anyio
async def test_deleting_record_cancels_jobs_and_removes_audio_cache(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, client):
        record_id = await seed_transcript_record(app, status="CONTENT_PROCESSING")
        cache_file = data_dir / "cache" / "audio" / record_id / "chunks" / "chunk-00000.ogg"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"cache")
        response = await client.delete(f"/api/records/{record_id}")

    assert response.status_code == 204
    assert not (data_dir / "cache" / "audio" / record_id).exists()


async def seed_segmented_record(
    app: FastAPI,
    *,
    file_ids: list[str],
    content: str,
    segments: list[dict[str, object]],
) -> str:
    """种子：可编辑记录（SUMMARY_READY）+ 文件 + 转写 + 既有分片，供对齐重切测试。"""
    record_id = str(uuid4())
    transcript_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, NULL, 'AUDIO_IMPORT', '音频', 'SUMMARY_READY', 60000, "
                "NULL, :now, :now, NULL)"
            ),
            {"id": record_id, "now": now},
        )
        for sequence_no, file_id in enumerate(file_ids):
            await session.execute(
                text(
                    "INSERT INTO record_files "
                    "(id, record_id, file_type, source_type, file_path, original_name, "
                    "mime_type, file_size, duration_ms, sequence_no, content_hash, "
                    "created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', :path, :name, "
                    "'audio/ogg', 1, 30000, :seq, 'h', :now, :now, NULL)"
                ),
                {
                    "id": file_id,
                    "record_id": record_id,
                    "path": f"files/{record_id}/{file_id}.ogg",
                    "name": f"{sequence_no + 1}.ogg",
                    "seq": sequence_no,
                    "now": now,
                },
            )
        await session.execute(
            text(
                "INSERT INTO transcripts "
                "(id, record_id, language, content, source_version, edited_by_user, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)"
            ),
            {"id": transcript_id, "record_id": record_id, "content": content, "now": now},
        )
        for segment in segments:
            await session.execute(
                text(
                    "INSERT INTO transcript_segments "
                    "(id, transcript_id, record_id, file_id, sequence_no, "
                    "record_start_ms, record_end_ms, file_start_ms, file_end_ms, speaker, "
                    "content, content_hash) "
                    "VALUES (:id, :tid, :rid, :fid, :seq, :rs, :re, :fs, :fe, NULL, "
                    ":content, :chash)"
                ),
                {"tid": transcript_id, "rid": record_id, **segment},
            )
    return record_id


def segment_row(
    segment_id: str,
    file_id: str,
    sequence_no: int,
    content: str,
    *,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, object]:
    return {
        "id": segment_id,
        "fid": file_id,
        "seq": sequence_no,
        "rs": start,
        "re": end,
        "fs": start,
        "fe": end,
        "content": content,
        "chash": content_hash(content),
    }


@pytest.mark.anyio
async def test_transcript_patch_realigns_segments_typo_insert_delete(tmp_path: Path) -> None:
    """改错别字句保留时间戳与 id；插入句 NULL；被删句分片移除。"""
    file_id = str(uuid4())
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_segmented_record(
            app,
            file_ids=[file_id],
            content="第一句\n第二句\n第三句",
            segments=[
                segment_row("seg-1", file_id, 0, "第一句", start=0, end=1000),
                segment_row("seg-2", file_id, 1, "第二句", start=1000, end=2000),
                segment_row("seg-3", file_id, 2, "第三句"),
            ],
        )
        updated = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "第一句\n第二句改动\n新增句", "expected_source_version": 1},
        )
        segments = (await client.get(f"/api/records/{record_id}/transcript/segments")).json()

    assert updated.status_code == 200
    assert [(row["content"], row["sequence_no"]) for row in segments] == [
        ("第一句", 0),
        ("第二句改动", 1),
        ("新增句", 2),
    ]
    assert segments[0]["id"] == "seg-1"
    assert all(row["id"] not in {"seg-1", "seg-2", "seg-3"} for row in segments[1:])
    assert segments[0]["record_start_ms"] == 0
    assert segments[0]["record_end_ms"] == 1000
    assert segments[0]["file_start_ms"] == 0
    assert segments[0]["file_end_ms"] == 1000
    assert all(row["record_start_ms"] is None for row in segments[1:])
    assert all(row["file_end_ms"] is None for row in segments[1:])


@pytest.mark.anyio
async def test_transcript_patch_new_sentence_inherits_neighbor_file(tmp_path: Path) -> None:
    """多文件记录：删除句移除；文件间新增句继承左侧最近命中句；前缀无命中回退右侧。"""
    file_one = str(uuid4())
    file_two = str(uuid4())
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_segmented_record(
            app,
            file_ids=[file_one, file_two],
            content="A句\nA二句\nB句",
            segments=[
                segment_row("seg-a1", file_one, 0, "A句", start=0, end=500),
                segment_row("seg-a2", file_one, 1, "A二句", start=500, end=1000),
                segment_row("seg-b1", file_two, 2, "B句", start=0, end=800),
            ],
        )
        updated = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "A句\nB句\nB句新增", "expected_source_version": 1},
        )
        segments = (await client.get(f"/api/records/{record_id}/transcript/segments")).json()
        async with app.state.session_factory() as session:
            file_owners = (
                await session.execute(
                    text(
                        "SELECT content, file_id FROM transcript_segments "
                        "WHERE record_id = :rid ORDER BY sequence_no"
                    ),
                    {"rid": record_id},
                )
            ).all()

        assert updated.status_code == 200
        assert [row["content"] for row in segments] == ["A句", "B句", "B句新增"]
        assert file_owners == [("A句", file_one), ("B句", file_two), ("B句新增", file_two)]
        assert segments[0]["record_start_ms"] == 0
        assert segments[1]["file_start_ms"] == 0
        assert segments[2]["file_start_ms"] is None

        # 前缀新增（其前无命中句）：回退右侧最近命中句的文件。
        updated_prefix = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "前缀新增\nA句\nB句", "expected_source_version": 2},
        )
        async with app.state.session_factory() as session:
            prefix_owner = (
                await session.execute(
                    text(
                        "SELECT file_id FROM transcript_segments WHERE record_id = :rid "
                        "AND sequence_no = 0"
                    ),
                    {"rid": record_id},
                )
            ).scalar_one()

    assert updated_prefix.status_code == 200
    assert prefix_owner == file_one


@pytest.mark.anyio
async def test_transcript_patch_full_rewrite_rebuilds_all_segments(tmp_path: Path) -> None:
    """整篇大改：全量重切不报错，旧行全部换新且时间戳为 NULL、序号连续。"""
    file_id = str(uuid4())
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_segmented_record(
            app,
            file_ids=[file_id],
            content="旧的一句\n旧的两句",
            segments=[
                segment_row("seg-old-1", file_id, 0, "旧的一句", start=0, end=400),
                segment_row("seg-old-2", file_id, 1, "旧的两句", start=400, end=900),
            ],
        )
        updated = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "完全不同的一句\n完全不同的另一句", "expected_source_version": 1},
        )
        segments = (await client.get(f"/api/records/{record_id}/transcript/segments")).json()

    assert updated.status_code == 200
    assert [row["content"] for row in segments] == ["完全不同的一句", "完全不同的另一句"]
    assert all(row["id"] not in {"seg-old-1", "seg-old-2"} for row in segments)
    assert [row["sequence_no"] for row in segments] == [0, 1]
    assert all(row["record_start_ms"] is None for row in segments)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
