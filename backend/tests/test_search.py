"""全局搜索服务：FTS5 索引检索、回填与过滤口径（只断言 HTTP 响应行为）。"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.llm.service import KnowledgePointModel, StructuredModelResult
from app.modules.search.service import SearchService

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_search_app(
    data_dir: Path,
    *,
    knowledge_point_model: KnowledgePointModel | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        knowledge_point_model=knowledge_point_model,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def seed_course(
    app: FastAPI,
    course_id: str,
    name: str,
    *,
    hot_words: str | None = None,
    status: str = "ACTIVE",
    deleted_at: str | None = None,
    updated_at: str = "2026-09-01T10:00:00.000000Z",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, hot_words, status, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :name, 'INTEREST', 'BEGINNER', :hot_words, :status, "
                ":updated_at, :updated_at, :deleted_at)"
            ),
            {
                "id": course_id,
                "name": name,
                "hot_words": hot_words,
                "status": status,
                "updated_at": updated_at,
                "deleted_at": deleted_at,
            },
        )


async def seed_record(
    app: FastAPI,
    record_id: str,
    *,
    course_id: str | None,
    title: str,
    deleted_at: str | None = None,
    updated_at: str = "2026-09-01T10:05:00.000000Z",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'RECORDING', :title, 'COMPLETED', 0, NULL, "
                ":updated_at, :updated_at, :deleted_at)"
            ),
            {
                "id": record_id,
                "course_id": course_id,
                "title": title,
                "updated_at": updated_at,
                "deleted_at": deleted_at,
            },
        )


async def seed_transcript(app: FastAPI, record_id: str, content: str) -> None:
    now = "2026-09-01T10:06:00.000000Z"
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at) "
                "VALUES (:id, :record_id, 'zh', :content, 1, 0, :now, :now)"
            ),
            {"id": str(uuid4()), "record_id": record_id, "content": content, "now": now},
        )


async def seed_knowledge_point(
    app: FastAPI,
    knowledge_point_id: str,
    record_id: str,
    name: str,
    *,
    detail: str = "知识点的详细说明",
    tags: str = "[]",
    generation_status: str = "ACTIVE",
    deleted_at: str | None = None,
    updated_at: str = "2026-09-01T10:10:00.000000Z",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO knowledge_points (id, record_id, name, detail, tags, importance, "
                "generation_status, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, :name, :detail, :tags, 3, :generation_status, "
                ":updated_at, :updated_at, :deleted_at)"
            ),
            {
                "id": knowledge_point_id,
                "record_id": record_id,
                "name": name,
                "detail": detail,
                "tags": tags,
                "generation_status": generation_status,
                "updated_at": updated_at,
                "deleted_at": deleted_at,
            },
        )


async def backfill(app: FastAPI) -> None:
    await SearchService.backfill_missing(app.state.session_factory)


async def index_row_count(app: FastAPI) -> int:
    async with app.state.session_factory() as session:
        return int(await session.scalar(text("SELECT count(*) FROM search_index")) or 0)


@pytest.mark.anyio
async def test_search_matches_two_char_chinese_word_across_entity_types(
    tmp_path: Path,
) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "线性代数")
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="线性代数第一讲",
        )
        await seed_transcript(
            app, "22222222-2222-4222-8222-222222222222", "今天介绍行列式的计算方法"
        )
        # 收件箱未归类记录：正文命中，course_name 应为 null。
        await seed_record(
            app,
            "33333333-3333-4333-8333-333333333333",
            course_id=None,
            title="课堂速记",
        )
        await seed_transcript(app, "33333333-3333-4333-8333-333333333333", "复习了线性代数的特征值")
        await seed_knowledge_point(
            app,
            "44444444-4444-4444-8444-444444444444",
            "22222222-2222-4222-8222-222222222222",
            "代数基本定理",
        )
        await backfill(app)

        response = await client.get("/api/search", params={"q": "代数"})

    assert response.status_code == 200
    payload = response.json()
    assert [course["id"] for course in payload["courses"]] == [
        "11111111-1111-4111-8111-111111111111"
    ]
    # 标题命中（第一讲）优先于正文命中（课堂速记）。
    assert [record["id"] for record in payload["records"]] == [
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    ]
    unclassified = payload["records"][1]
    assert unclassified["title"] == "课堂速记"
    assert unclassified["course_name"] is None
    assert "线性代数" in unclassified["snippet"]
    assert [knowledge_point["id"] for knowledge_point in payload["knowledge_points"]] == [
        "44444444-4444-4444-8444-444444444444"
    ]
    knowledge_point = payload["knowledge_points"][0]
    assert knowledge_point["record_id"] == "22222222-2222-4222-8222-222222222222"
    assert knowledge_point["course_name"] == "线性代数"
    assert knowledge_point["updated_at"] == "2026-09-01T10:10:00.000000Z"


@pytest.mark.anyio
async def test_search_matches_tags_and_hot_words(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(
            app,
            "11111111-1111-4111-8111-111111111111",
            "高等数学",
            hot_words='["傅里叶级数"]',
        )
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="高等数学第三讲",
        )
        await seed_knowledge_point(
            app,
            "33333333-3333-4333-8333-333333333333",
            "22222222-2222-4222-8222-222222222222",
            "级数收敛判据",
            tags='["微积分"]',
        )
        await backfill(app)

        by_tag = await client.get("/api/search", params={"q": "微积分"})
        by_hot_word = await client.get("/api/search", params={"q": "傅里叶"})

    assert by_tag.status_code == 200
    assert [item["id"] for item in by_tag.json()["knowledge_points"]] == [
        "33333333-3333-4333-8333-333333333333"
    ]
    assert by_tag.json()["courses"] == []
    assert by_hot_word.status_code == 200
    assert [item["id"] for item in by_hot_word.json()["courses"]] == [
        "11111111-1111-4111-8111-111111111111"
    ]


@pytest.mark.anyio
async def test_search_ranks_title_hit_above_body_hit(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "高等数学")
        # 标题含「行列式」、正文不含；另一条正文含、标题不含。
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="行列式计算技巧",
        )
        await seed_transcript(app, "22222222-2222-4222-8222-222222222222", "本讲介绍常见方法")
        await seed_record(
            app,
            "33333333-3333-4333-8333-333333333333",
            course_id="11111111-1111-4111-8111-111111111111",
            title="线性代数习题课",
        )
        await seed_transcript(
            app, "33333333-3333-4333-8333-333333333333", "今天的主题是行列式的应用举例"
        )
        await backfill(app)

        response = await client.get("/api/search", params={"q": "行列式"})

    assert response.status_code == 200
    payload = response.json()
    assert [record["id"] for record in payload["records"]] == [
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    ]
    assert "行列式" in payload["records"][1]["snippet"]


@pytest.mark.anyio
async def test_search_filters_soft_deleted_and_restored(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "高等数学")
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="极限专题",
        )
        await seed_knowledge_point(
            app,
            "33333333-3333-4333-8333-333333333333",
            "22222222-2222-4222-8222-222222222222",
            "极限的夹逼定理",
        )
        # SUPERSEDED 知识点与默认视图口径一致：不进结果。
        await seed_knowledge_point(
            app,
            "44444444-4444-4444-8444-444444444444",
            "22222222-2222-4222-8222-222222222222",
            "极限的历史版本",
            generation_status="SUPERSEDED",
        )
        await backfill(app)

        visible = await client.get("/api/search", params={"q": "极限"})
        assert [record["id"] for record in visible.json()["records"]] == [
            "22222222-2222-4222-8222-222222222222"
        ]
        assert [item["id"] for item in visible.json()["knowledge_points"]] == [
            "33333333-3333-4333-8333-333333333333"
        ]

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET deleted_at = '2026-09-01T12:00:00.000000Z' "
                    "WHERE id = '22222222-2222-4222-8222-222222222222'"
                )
            )
            await session.execute(
                text(
                    "UPDATE knowledge_points SET deleted_at = '2026-09-01T12:00:00.000000Z' "
                    "WHERE id = '33333333-3333-4333-8333-333333333333'"
                )
            )
        hidden = await client.get("/api/search", params={"q": "极限"})
        assert hidden.json()["records"] == []
        # 记录软删连带其知识点不可见。
        assert [item["id"] for item in hidden.json()["knowledge_points"]] == []

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET deleted_at = NULL "
                    "WHERE id = '22222222-2222-4222-8222-222222222222'"
                )
            )
            await session.execute(
                text(
                    "UPDATE knowledge_points SET deleted_at = NULL "
                    "WHERE id = '33333333-3333-4333-8333-333333333333'"
                )
            )
        restored = await client.get("/api/search", params={"q": "极限"})
        assert [record["id"] for record in restored.json()["records"]] == [
            "22222222-2222-4222-8222-222222222222"
        ]
        assert [item["id"] for item in restored.json()["knowledge_points"]] == [
            "33333333-3333-4333-8333-333333333333"
        ]


@pytest.mark.anyio
async def test_search_excludes_archived_course_tree(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "线性代数")
        await seed_course(app, "55555555-5555-4555-8555-555555555555", "高等数学")
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="线性代数第一讲",
        )
        await seed_knowledge_point(
            app,
            "33333333-3333-4333-8333-333333333333",
            "22222222-2222-4222-8222-222222222222",
            "线性代数基础概念",
        )
        await seed_record(
            app,
            "44444444-4444-4444-8444-444444444444",
            course_id="55555555-5555-4555-8555-555555555555",
            title="线性代数在工程中的应用",
        )
        await backfill(app)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status = 'ARCHIVED' "
                    "WHERE id = '11111111-1111-4111-8111-111111111111'"
                )
            )
        response = await client.get("/api/search", params={"q": "线性代数"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["courses"] == []
    assert [record["id"] for record in payload["records"]] == [
        "44444444-4444-4444-8444-444444444444"
    ]
    assert payload["knowledge_points"] == []


@pytest.mark.anyio
async def test_search_applies_per_group_limit(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "高等数学")
        for index in range(1, 8):
            await seed_record(
                app,
                f"22222222-2222-4222-8222-22222222222{index}",
                course_id="11111111-1111-4111-8111-111111111111",
                title=f"极限练习第{index}讲",
            )
        await backfill(app)

        default_limit = await client.get("/api/search", params={"q": "极限"})
        small_limit = await client.get("/api/search", params={"q": "极限", "limit": 3})

    assert len(default_limit.json()["records"]) == 5
    assert len(small_limit.json()["records"]) == 3


@pytest.mark.anyio
async def test_search_rejects_blank_missing_or_overlong_query(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (_app, client):
        missing = await client.get("/api/search")
        blank = await client.get("/api/search", params={"q": "   "})
        overlong = await client.get("/api/search", params={"q": "词" * 101})
        zero_limit = await client.get("/api/search", params={"q": "代数", "limit": 0})
        huge_limit = await client.get("/api/search", params={"q": "代数", "limit": 51})

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert overlong.status_code == 422
    assert zero_limit.status_code == 422
    assert huge_limit.status_code == 422


@pytest.mark.anyio
async def test_backfill_is_idempotent_and_covers_new_rows(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, "11111111-1111-4111-8111-111111111111", "线性代数")
        await seed_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id="11111111-1111-4111-8111-111111111111",
            title="特征值专题",
        )
        await backfill(app)
        first_count = await index_row_count(app)

        # 重复回填：不重复插行。
        await backfill(app)
        assert await index_row_count(app) == first_count

        # 新增存量（绕过写路径）：回填后可搜（不遗漏）。
        await seed_record(
            app,
            "33333333-3333-4333-8333-333333333333",
            course_id=None,
            title="向量空间补充笔记",
        )
        await backfill(app)
        assert await index_row_count(app) == first_count + 1

        response = await client.get("/api/search", params={"q": "向量"})

    assert response.status_code == 200
    assert [record["id"] for record in response.json()["records"]] == [
        "33333333-3333-4333-8333-333333333333"
    ]


class FakeKnowledgePointModel:
    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        return StructuredModelResult(
            output={
                "items": [
                    {
                        "name": "循环神经网络",
                        "detail": "循环结构能够记忆上下文信息。",
                        "tags": ["深度学习"],
                        "importance": 5,
                    }
                ]
            },
            token_usage={"total_tokens": 21},
        )


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


async def wait_for_knowledge_point_action(
    client: httpx.AsyncClient,
    record_id: str,
    action: str,
) -> dict[str, object]:
    for _ in range(250):
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/knowledge-points")).json(),
        )
        if payload.get("action_required") == action:
            return payload
        await asyncio.sleep(0.02)
    pytest.fail(f"知识点状态未进入 {action}")


@pytest.mark.anyio
async def test_text_capture_title_and_body_are_searchable(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (_app, client):
        created = await client.post(
            "/api/text-captures",
            json={
                "capture_type": "QUICK_NOTE",
                "content": "梯度下降法通过迭代更新参数\n逐步最小化损失函数",
            },
        )
        assert created.status_code == 201
        record_id = cast(str, created.json()["record_id"])

        by_title = await client.get("/api/search", params={"q": "梯度"})
        by_body = await client.get("/api/search", params={"q": "损失"})

    assert [record["id"] for record in by_title.json()["records"]] == [record_id]
    assert [record["id"] for record in by_body.json()["records"]] == [record_id]


@pytest.mark.anyio
async def test_document_import_and_transcript_finalize_are_searchable(
    tmp_path: Path,
) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (_app, client):
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

        by_title = await client.get("/api/search", params={"q": "行列式"})
        by_body = await client.get("/api/search", params={"q": "傅里叶"})

    assert [record["id"] for record in by_title.json()["records"]] == [record_id]
    assert [record["id"] for record in by_body.json()["records"]] == [record_id]


@pytest.mark.anyio
async def test_transcript_edit_makes_new_word_searchable_and_old_word_miss(
    tmp_path: Path,
) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        record_id = "22222222-2222-4222-8222-222222222222"
        await seed_record(app, record_id, course_id=None, title="课堂速记")
        await seed_transcript(app, record_id, "本讲回顾行列式的几何意义")
        await backfill(app)

        edited = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={
                "content": "修订后的主题是傅里叶级数的收敛判据",
                "expected_source_version": 1,
            },
        )
        assert edited.status_code == 200
        by_new = await client.get("/api/search", params={"q": "傅里叶"})
        by_old = await client.get("/api/search", params={"q": "行列式"})

    assert [record["id"] for record in by_new.json()["records"]] == [record_id]
    assert by_old.json()["records"] == []


@pytest.mark.anyio
async def test_knowledge_point_create_and_edit_sync_index(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        record_id = "22222222-2222-4222-8222-222222222222"
        await seed_record(app, record_id, course_id=None, title="课堂速记")

        created = await client.post(
            f"/api/records/{record_id}/knowledge-points",
            json={
                "name": "矩阵的秩",
                "detail": "秩刻画列空间的维数。",
                "tags": ["线性代数"],
                "importance": 3,
            },
        )
        assert created.status_code == 201
        item_id = cast(str, created.json()["id"])
        by_created = await client.get("/api/search", params={"q": "矩阵"})
        assert [item["id"] for item in by_created.json()["knowledge_points"]] == [item_id]

        updated = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{item_id}",
            json={
                "name": "向量空间",
                "detail": "向量空间由基底张成。",
                "tags": ["线性代数"],
                "importance": 3,
            },
        )
        assert updated.status_code == 200
        by_new = await client.get("/api/search", params={"q": "向量"})
        by_old = await client.get("/api/search", params={"q": "矩阵"})

    assert [item["id"] for item in by_new.json()["knowledge_points"]] == [item_id]
    assert by_old.json()["knowledge_points"] == []


@pytest.mark.anyio
async def test_knowledge_point_regeneration_and_confirm_sync_index(
    tmp_path: Path,
) -> None:
    async with running_search_app(
        tmp_path / "KnowRealm",
        knowledge_point_model=FakeKnowledgePointModel(),
    ) as (app, client):
        course = await client.post(
            "/api/courses",
            json={"name": "深度学习", "learning_context": "INTEREST", "depth": "BEGINNER"},
        )
        course_id = cast(str, course.json()["id"])
        record_id = "22222222-2222-4222-8222-222222222222"
        now = "2026-09-01T11:00:00.000000Z"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO records (id, course_id, capture_type, title, status, "
                    "duration_ms, summary_confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', '深度学习第一讲', "
                    "'COMPLETED', 0, :now, :now, :now, NULL)"
                ),
                {"id": record_id, "course_id": course_id, "now": now},
            )
            await session.execute(
                text(
                    "INSERT INTO transcripts (id, record_id, language, content, "
                    "source_version, edited_by_user, created_at, updated_at) "
                    "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now)"
                ),
                {
                    "id": str(uuid4()),
                    "record_id": record_id,
                    "content": "本讲介绍序列建模的基本思路。",
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO ai_summaries (id, record_id, version_no, "
                    "transcript_source_version, topic, abstract, summary_json, status, "
                    "model, prompt_version, token_usage_json, latency_ms, user_feedback, "
                    "confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 1, 1, '序列建模', :abstract, :summary_json, "
                    "'CONFIRMED', 'qwen-plus', 'summary-v1', '{}', 10, NULL, :now, :now, "
                    ":now, NULL)"
                ),
                {
                    "id": str(uuid4()),
                    "record_id": record_id,
                    "abstract": "总结介绍序列建模与记忆机制。" * 40,
                    "summary_json": json.dumps(
                        {"sections": [{"heading": "建模", "points": ["序列建模依赖记忆。"]}]},
                        ensure_ascii=False,
                    ),
                    "now": now,
                },
            )
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

        submitted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        assert submitted.status_code == 202
        payload = await wait_for_knowledge_point_action(client, record_id, "CONFIRM")

        # 重新生成落 DRAFT 行：writeback 事务内入索引，立即按名称可搜。
        by_draft = await client.get("/api/search", params={"q": "神经网络"})
        draft_items = cast(list[dict[str, object]], by_draft.json()["knowledge_points"])
        assert len(draft_items) == 1
        item_id = cast(str, draft_items[0]["id"])
        items = cast(list[dict[str, object]], payload["items"])
        batch_ids = {
            cast(str, item["batch_id"])
            for item in items
            if item["generation_status"] == "DRAFT"
        }
        assert len(batch_ids) == 1

        # 抽走索引行模拟缺行旧数据：确认事务应同事务补行。
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "DELETE FROM search_index "
                    "WHERE entity_type = 'knowledge_point' AND entity_id = :id"
                ),
                {"id": item_id},
            )
        confirmed = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_ids.pop()}/confirmations"
        )
        assert confirmed.status_code == 200
        by_confirmed = await client.get("/api/search", params={"q": "神经网络"})

    assert [item["id"] for item in by_confirmed.json()["knowledge_points"]] == [item_id]


@pytest.mark.anyio
async def test_course_create_rename_and_hot_words_sync_index(tmp_path: Path) -> None:
    async with running_search_app(tmp_path / "KnowRealm") as (_app, client):
        created = await client.post(
            "/api/courses",
            json={"name": "量子力学导论", "learning_context": "INTEREST", "depth": "BEGINNER"},
        )
        assert created.status_code == 201
        course_id = cast(str, created.json()["id"])
        by_name = await client.get("/api/search", params={"q": "量子"})
        assert [course["id"] for course in by_name.json()["courses"]] == [course_id]

        renamed = await client.patch(
            f"/api/courses/{course_id}", json={"name": "统计力学入门"}
        )
        assert renamed.status_code == 200
        by_new = await client.get("/api/search", params={"q": "统计"})
        by_old = await client.get("/api/search", params={"q": "量子"})
        assert [course["id"] for course in by_new.json()["courses"]] == [course_id]
        assert by_old.json()["courses"] == []

        hot_words_set = await client.patch(
            f"/api/courses/{course_id}", json={"hot_words": ["傅里叶变换"]}
        )
        assert hot_words_set.status_code == 200
        by_hot_word = await client.get("/api/search", params={"q": "傅里叶"})

    assert [course["id"] for course in by_hot_word.json()["courses"]] == [course_id]


@pytest.mark.anyio
async def test_index_sync_failure_rolls_back_business_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_upsert(session: object, record_id: str) -> None:
        raise RuntimeError("index sync failed")

    async with running_search_app(tmp_path / "KnowRealm") as (app, client):
        record_id = "22222222-2222-4222-8222-222222222222"
        await seed_record(app, record_id, course_id=None, title="课堂速记")
        await seed_transcript(app, record_id, "本讲回顾行列式的几何意义")
        await backfill(app)
        monkeypatch.setattr(SearchService, "upsert_record_index", staticmethod(failing_upsert))

        failed = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={
                "content": "修订后的主题是傅里叶级数的收敛判据",
                "expected_source_version": 1,
            },
        )
        assert failed.status_code == 500

        transcript = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/transcript")).json(),
        )
        transcript_body = cast(dict[str, object], transcript["transcript"])
        assert transcript_body["content"] == "本讲回顾行列式的几何意义"
        by_old = await client.get("/api/search", params={"q": "行列式"})
        by_new = await client.get("/api/search", params={"q": "傅里叶"})

    assert [record["id"] for record in by_old.json()["records"]] == [record_id]
    assert by_new.json()["records"] == []

