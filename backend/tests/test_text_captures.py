import asyncio
import shutil
import struct
import wave
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.llm import SummaryModel, SummaryModelResult
from app.schemas.summary import SummaryContent, SummarySection
from app.services.tencent_asr_client import (
    TencentAsrClient,
    TencentAsrCredentials,
    TencentAsrTask,
    TencentAsrTaskStatus,
)

TOKEN = "test-launch-token"
MIB = 1024 * 1024


class SuccessfulAsrClient(TencentAsrClient):
    async def is_online(self) -> bool:
        return True

    async def submit(
        self,
        path: Path,
        credentials: TencentAsrCredentials,
        config: dict[str, object],
    ) -> str:
        return "task-1"

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        return TencentAsrTask(status=TencentAsrTaskStatus.SUCCEEDED, text="mixed audio body")


class FakeSummaryModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult:
        self.prompts.append(prompt)
        return SummaryModelResult(
            output=SummaryContent(
                topic="速记主题",
                abstract="用于验证文本捕获总结入队的合成摘要。" * 30,
                sections=[
                    SummarySection(heading="核心内容", points=["合成要点，不依赖真实供应商。"])
                ],
            ),
            token_usage={"total_tokens": 1},
        )


@asynccontextmanager
async def running_app(
    data_dir: Path,
    *,
    summary_model: SummaryModel | None = None,
    ffmpeg_path: Path | None = None,
    asr_client: TencentAsrClient | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient], None]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        summary_model=summary_model,
        ffmpeg_path=ffmpeg_path,
        asr_client=asr_client,
    )
    app.exception_handlers.pop(Exception, None)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def create_course(client: httpx.AsyncClient, name: str = "文本课程") -> str:
    response = await client.post(
        "/api/courses",
        json={"name": name, "learning_context": "INTEREST", "depth": "BEGINNER"},
    )
    assert response.status_code == 201
    return cast(str, response.json()["id"])


async def configure_llm(client: httpx.AsyncClient) -> None:
    provider = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert provider.status_code == 200
    consent = await client.post("/api/settings/external-processing-consents/llm")
    assert consent.status_code == 200


async def business_counts(app: FastAPI, record_id: str) -> tuple[int, int, int]:
    async with app.state.session_factory() as session:
        record_count = await session.scalar(
            text("SELECT count(*) FROM records WHERE id = :id"), {"id": record_id}
        )
        file_count = await session.scalar(
            text("SELECT count(*) FROM record_files WHERE record_id = :id"),
            {"id": record_id},
        )
        job_count = await session.scalar(
            text("SELECT count(*) FROM processing_jobs WHERE record_id = :id"),
            {"id": record_id},
        )
        return (
            cast(int, record_count),
            cast(int, file_count),
            cast(int, job_count),
        )


def post_text(
    client: httpx.AsyncClient,
    capture_type: str,
    content: str,
    course_id: str | None = None,
):
    return client.post(
        "/api/text-captures",
        json={
            "capture_type": capture_type,
            "content": content,
            **({"course_id": course_id} if course_id is not None else {}),
        },
    )


@pytest.mark.anyio
async def test_quick_note_creates_record_and_transcript_without_sources_or_jobs(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        response = await post_text(client, "QUICK_NOTE", "  \n速记首行\n\n第二段\r\n带 CR 行")

        assert response.status_code == 201
        accepted = cast(dict[str, object], response.json())
        assert accepted["summary_job_id"] is None
        record_id = cast(str, accepted["record_id"])
        record = (await client.get(f"/api/records/{record_id}")).json()
        transcript = (await client.get(f"/api/records/{record_id}/transcript")).json()["transcript"]
        counts = await business_counts(app, record_id)

    assert record["course_id"] is None
    assert record["capture_type"] == "QUICK_NOTE"
    assert record["status"] == "NOTE"
    assert record["title"] == "速记首行"
    assert transcript["language"] == "und"
    assert transcript["source_version"] == 1
    assert transcript["edited_by_user"] is False
    assert transcript["content"] == "  \n速记首行\n\n第二段\n带 CR 行"
    assert counts == (1, 0, 0)


@pytest.mark.anyio
async def test_paste_without_course_is_note_and_with_active_course_is_summary_pending(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        unclassified = await post_text(client, "PASTE", "未归类粘贴\n正文")
        course_id = await create_course(client)
        classified = await post_text(client, "PASTE", "已归类粘贴", course_id)

        assert unclassified.status_code == 201
        unclassified_record = (
            await client.get(f"/api/records/{unclassified.json()['record_id']}")
        ).json()
        assert classified.status_code == 201
        classified_record = (
            await client.get(f"/api/records/{classified.json()['record_id']}")
        ).json()

    assert unclassified_record["status"] == "NOTE"
    assert unclassified_record["course_id"] is None
    assert classified_record["status"] == "SUMMARY_PENDING"
    assert classified_record["course_id"] == course_id


@pytest.mark.anyio
async def test_paste_with_course_enqueues_summary_only_when_provider_and_consent_exist(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (_app, client):
        course_id = await create_course(client)
        without_provider = await post_text(client, "PASTE", "无 Provider 粘贴", course_id)
        await configure_llm(client)
        with_provider = await post_text(client, "PASTE", "有 Provider 粘贴", course_id)

        assert without_provider.status_code == 201
        assert without_provider.json()["summary_job_id"] is None
        assert with_provider.status_code == 201
        summary_job_id = with_provider.json()["summary_job_id"]
        assert summary_job_id is not None
        for _ in range(250):
            if fake.prompts:
                break
            await asyncio.sleep(0.02)

    assert len(fake.prompts) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capture_type", "course", "expected_status", "detail"),
    [
        ("QUICK_NOTE", "present", 422, "QUICK_NOTE_NO_COURSE"),
        ("RECORDING", None, 422, "UNSUPPORTED_TEXT_CAPTURE"),
        ("PASTE", "missing", 404, "课程不存在或已删除"),
        ("PASTE", "archived", 409, "已归档课程不能接受新资料"),
    ],
)
async def test_invalid_text_capture_combinations_are_rejected_without_business_rows(
    tmp_path: Path,
    capture_type: str,
    course: str,
    expected_status: int,
    detail: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client)
        if course == "archived":
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                    {"id": course_id},
                )
        course_id = course_id if course in ("present", "archived", "missing") else None
        if course == "missing":
            course_id = "99999999-9999-4999-8999-999999999999"
        response = await post_text(client, capture_type, "正文", course_id)
        async with app.state.session_factory() as session:
            counts = [
                await session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("records", "transcripts", "record_files", "processing_jobs")
            ]

    assert response.status_code == expected_status
    assert detail in response.json()["detail"]
    assert counts == [0, 0, 0, 0]


@pytest.mark.anyio
@pytest.mark.parametrize("content", [" \n\t\r\n ", ""])
async def test_blank_content_is_rejected_before_business_rows(
    tmp_path: Path,
    content: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        response = await post_text(client, "QUICK_NOTE", content)
        async with app.state.session_factory() as session:
            counts = [
                await session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("records", "transcripts")
            ]

    assert response.status_code == 422
    assert counts == [0, 0]


@pytest.mark.anyio
async def test_content_is_limited_to_exactly_one_mib_without_truncation(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, client):
        exactly = await post_text(client, "QUICK_NOTE", "a" * MIB)
        oversized = await post_text(client, "QUICK_NOTE", "字" * (MIB // 3 + 1))
        async with app.state.session_factory() as session:
            records = await session.scalar(text("SELECT count(*) FROM records"))
        transcript = (
            await client.get(f"/api/records/{exactly.json()['record_id']}/transcript")
        ).json()["transcript"]

    assert exactly.status_code == 201
    assert oversized.status_code == 422
    assert "TEXT_TOO_LARGE" in oversized.json()["detail"]
    assert "TXT" in oversized.json()["detail"]
    assert records == 1
    assert len(transcript["content"]) == MIB


@pytest.mark.anyio
async def test_title_takes_first_nonempty_line_limited_to_100_unicode_chars(
    tmp_path: Path,
) -> None:
    long_line = "标题" + "细" * 200
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        response = await post_text(client, "PASTE", f"\n  \n{long_line}\n\n后续段落")

        assert response.status_code == 201
        record = (await client.get(f"/api/records/{response.json()['record_id']}")).json()

    assert record["title"] == long_line[:100]


@pytest.mark.anyio
async def test_transcript_failure_leaves_no_half_record(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "CREATE TRIGGER reject_text_transcripts BEFORE INSERT ON transcripts "
                    "BEGIN SELECT RAISE(ABORT, 'forced transcript failure'); END"
                )
            )
        with pytest.raises(Exception, match="forced transcript failure"):
            await post_text(client, "QUICK_NOTE", "原子性正文")
        async with app.state.session_factory() as session:
            counts = [
                await session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("records", "transcripts")
            ]

    assert counts == [0, 0]


@pytest.mark.anyio
async def test_text_capture_requires_launch_token(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        client.headers.pop("X-KnowRealm-Token")
        response = await post_text(client, "QUICK_NOTE", "无令牌")

    assert response.status_code == 403


@pytest.mark.anyio
async def test_inbox_lists_unclassified_records_in_stable_descending_order(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, client):
        course_id = await create_course(client)
        first = await post_text(client, "QUICK_NOTE", "第一条")
        await post_text(client, "PASTE", "第二条")
        classified = await post_text(client, "PASTE", "已归类", course_id)
        batch = await client.post(
            "/api/capture-batches",
            files=[("files", ("notes.txt", b"document body", "text/plain"))],
        )
        assert batch.status_code == 202
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET created_at = '2026-08-23T00:00:00.000000Z' "
                    "WHERE course_id IS NULL"
                )
            )
        inbox = await client.get("/api/inbox")
        deleted_id = first.json()["record_id"]
        await client.delete(f"/api/records/{deleted_id}")
        after_delete = await client.get("/api/inbox")

    assert inbox.status_code == 200
    entries = cast(list[dict[str, object]], inbox.json())
    ids = [cast(str, entry["id"]) for entry in entries]
    assert deleted_id in ids
    assert cast(str, classified.json()["record_id"]) not in ids
    assert ids == sorted(ids, reverse=True)
    statuses = {cast(str, entry["id"]): cast(str, entry["status"]) for entry in entries}
    assert statuses[batch.json()["record_id"]] == "CONTENT_PROCESSING"
    after_delete_ids = [cast(str, entry["id"]) for entry in after_delete.json()]
    assert deleted_id not in after_delete_ids
    assert len(after_delete_ids) == len(ids) - 1

    async with running_app(data_dir) as (_app2, client2):
        restarted = await client2.get("/api/inbox")

    restarted_ids = [cast(str, entry["id"]) for entry in restarted.json()]
    assert restarted_ids == after_delete_ids


@pytest.mark.anyio
async def test_unclassified_document_batches_finish_at_summary_pending_without_summary_calls(
    tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("真实 ffmpeg 不可用")
    data_dir = tmp_path / "KnowRealm"
    (data_dir / "config").mkdir(parents=True)
    (data_dir / "config" / "providers.json").write_text(
        '{"tencent_asr":{"secret_id":"id","secret_key":"key","region":"ap-shanghai"},'
        '"llm":{"base_url":"https://example.com/v1","api_key":"sk-test","model":"qwen-plus"}}',
        encoding="utf-8",
    )
    (data_dir / "config" / "settings.json").write_text(
        '{"tencent_asr_consent_granted_at":"2026-08-23T00:00:00Z",'
        '"llm_consent_granted_at":"2026-08-23T00:00:00Z"}',
        encoding="utf-8",
    )
    fake_summary = FakeSummaryModel()
    async with running_app(
        data_dir,
        summary_model=fake_summary,
        ffmpeg_path=Path(ffmpeg),
        asr_client=SuccessfulAsrClient(),
    ) as (_app, client):
        doc_only = await client.post(
            "/api/capture-batches",
            files=[("files", ("solo.txt", b"solo body", "text/plain"))],
        )
        multi_doc = await client.post(
            "/api/capture-batches",
            files=[
                ("files", ("first.txt", b"first body", "text/plain")),
                ("files", ("second.md", b"second body", "text/markdown")),
            ],
        )
        mixed = None
        output = BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(
                b"".join(
                    struct.pack("<h", int(8_000 * (2**0.5) * (i % 100) / 100))
                    for i in range(16_000 // 5)
                )
            )
        audio_only = await client.post(
            "/api/capture-batches",
            files=[("files", ("voice.wav", output.getvalue(), "audio/wav"))],
        )
        mixed = await client.post(
            "/api/capture-batches",
            files=[
                ("files", ("voice.wav", output.getvalue(), "audio/wav")),
                ("files", ("notes.txt", b"mixed document body", "text/plain")),
            ],
        )
        assert doc_only.status_code == 202
        assert multi_doc.status_code == 202
        assert audio_only.status_code == 202
        assert mixed is not None and mixed.status_code == 202
        record_ids = [
            cast(str, doc_only.json()["record_id"]),
            cast(str, multi_doc.json()["record_id"]),
            cast(str, audio_only.json()["record_id"]),
            cast(str, mixed.json()["record_id"]),
        ]
        final_statuses: list[str] = []
        for record_id in record_ids:
            status = ""
            for _ in range(250):
                status = cast(
                    str,
                    (await client.get(f"/api/records/{record_id}")).json()["status"],
                )
                if status != "CONTENT_PROCESSING":
                    break
                await asyncio.sleep(0.02)
            final_statuses.append(status)
        inbox = cast(list[dict[str, object]], (await client.get("/api/inbox")).json())

    assert final_statuses == [
        "SUMMARY_PENDING",
        "SUMMARY_PENDING",
        "SUMMARY_PENDING",
        "SUMMARY_PENDING",
    ]
    inbox_ids = {cast(str, entry["id"]) for entry in inbox}
    assert set(record_ids) <= inbox_ids
    assert fake_summary.prompts == []


@pytest.mark.anyio
async def test_legacy_document_import_accepts_nullable_course(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        unclassified = await client.post(
            "/api/document-imports",
            files=[("file", ("notes.txt", b"legacy body", "text/plain"))],
        )
        course_id = await create_course(client)
        classified = await client.post(
            "/api/document-imports",
            data={"course_id": course_id},
            files=[("file", ("notes.txt", b"legacy body", "text/plain"))],
        )

        assert unclassified.status_code == 202
        unclassified_record = (
            await client.get(f"/api/records/{unclassified.json()['record_id']}")
        ).json()
        assert classified.status_code == 202
        classified_record = (
            await client.get(f"/api/records/{classified.json()['record_id']}")
        ).json()

    assert unclassified_record["course_id"] is None
    assert classified_record["course_id"] == course_id


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
