"""Concept Mastery V1：纯函数算法黄金样本、窗口与状态规则、迁移结构。

黄金样本是数值合同（spec「Mastery 算法 V1」）：冻结 3 全对、4 错后 4 对、
4 对后 4 错、8 次交替（最新为错）、6 错后 6 对的分数与状态，不能只靠端到端间接覆盖。
"""

import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.learning.consumer import EvidenceConsumer
from app.modules.learning.mastery import (
    ALGORITHM_VERSION,
    MIN_EVIDENCE_COUNT,
    WINDOW_SIZE,
    MasteryConfidence,
    MasteryEvidence,
    MasteryStatus,
    compute_mastery,
    confidence_level_of,
)
from app.modules.learning.service import MasteryService

BASE_TIME = datetime(2026, 9, 1, 8, 0, 0)
TOKEN = "test-launch-token"
COURSE_ID = "11111111-1111-4111-8111-111111111111"
RECORD_ID = "22222222-2222-4222-8222-222222222222"
CONCEPT_ID = "33333333-3333-4333-8333-333333333331"
OTHER_CONCEPT_ID = "33333333-3333-4333-8333-333333333332"
ARCHIVED_CONCEPT_ID = "33333333-3333-4333-8333-333333333333"
NOW = "2026-09-01T08:00:00.000000Z"


async def seed_course_and_concepts(
    app: FastAPI,
    *,
    concepts: list[tuple[str, str, str]] | None = None,
) -> None:
    """种课程、未删除记录与概念列表（id, 名称, 状态）；默认两条 CONFIRMED。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, education_stage, depth, "
                "course_type, description, hot_words, status, created_at, updated_at, deleted_at) "
                "VALUES (:course_id, '操作系统', 'SCHOOL', 'UNDERGRADUATE', NULL, NULL, NULL, "
                "'[]', 'ACTIVE', :now, :now, NULL)"
            ),
            {"course_id": COURSE_ID, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:record_id, :course_id, 'DOCUMENT_IMPORT', '进程调度', 'COMPLETED', 0, "
                ":now, :now, :now, NULL)"
            ),
            {"record_id": RECORD_ID, "course_id": COURSE_ID, "now": NOW},
        )
        for concept_id, name, status in concepts or [
            (CONCEPT_ID, "进程调度", "CONFIRMED"),
            (OTHER_CONCEPT_ID, "内存分页", "CONFIRMED"),
        ]:
            await session.execute(
                text(
                    "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                    "description, concept_type, importance, status, source, created_at, "
                    "updated_at) VALUES (:concept_id, :course_id, :name, :name, '', 'TERM', 3, "
                    ":status, 'AI_EXTRACTED', :now, :now)"
                ),
                {
                    "concept_id": concept_id,
                    "course_id": COURSE_ID,
                    "name": name,
                    "status": status,
                    "now": NOW,
                },
            )


async def seed_active_quiz(app: FastAPI, *, quiz_id: str, concept_id: str | None) -> None:
    """种一道已采用（ACTIVE）的选择题，供 HTTP 作答接缝使用。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO quizzes (id, record_id, batch_id, generated_from_summary_id, "
                "generation_status, question_type, stem, options_json, correct_answer_json, "
                "explanation, difficulty, concept_id, created_at, updated_at, deleted_at) "
                "VALUES (:quiz_id, :record_id, NULL, NULL, 'ACTIVE', 'MULTIPLE_CHOICE', "
                "'进程调度的作用是什么？', '[\"分配处理器\", \"整理磁盘\"]', '0', "
                "'调度器选择就绪进程占用处理器。', 'EASY', :concept_id, :now, :now, NULL)"
            ),
            {
                "quiz_id": quiz_id,
                "record_id": RECORD_ID,
                "concept_id": concept_id,
                "now": NOW,
            },
        )


@asynccontextmanager
async def running_mastery_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


def evidence(
    *,
    score: float,
    index: int = 0,
    result: str | None = None,
    weight: float = 0.9,
    confidence: float = 0.8,
    occurred_at: datetime | None = None,
) -> MasteryEvidence:
    """构造一条标准 Quiz 证据；index 越大越新（occurred_at 递增）。"""
    return MasteryEvidence(
        evidence_id=f"evidence-{index:02d}",
        score=score,
        weight=weight,
        confidence=confidence,
        result=result if result is not None else ("CORRECT" if score >= 0.5 else "WRONG"),
        occurred_at=occurred_at if occurred_at is not None else BASE_TIME + timedelta(hours=index),
    )


def sequence(scores: list[float]) -> list[MasteryEvidence]:
    """按「最旧 → 最新」给出一组成绩序列。"""
    return [evidence(score=score, index=index) for index, score in enumerate(scores)]


GOLDEN_CASES = [
    (
        "3 次全对",
        [1.0, 1.0, 1.0],
        1.0,
        MasteryStatus.LEARNING,
        MasteryConfidence.LOW,
        3,
        0,
    ),
    (
        "4 错后 4 对",
        [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0],
        0.6666666666666666,
        MasteryStatus.LEARNING,
        MasteryConfidence.HIGH,
        4,
        4,
    ),
    (
        "4 对后 4 错",
        [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        0.3333333333333333,
        MasteryStatus.WEAK,
        MasteryConfidence.HIGH,
        4,
        4,
    ),
    (
        "8 次交替（最新为错）",
        [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        0.4567863831370551,
        MasteryStatus.WEAK,
        MasteryConfidence.HIGH,
        4,
        4,
    ),
    (
        "6 错后 6 对",
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        0.7387961250362587,
        MasteryStatus.LEARNING,
        MasteryConfidence.HIGH,
        6,
        6,
    ),
]


@pytest.mark.parametrize(
    (
        "name",
        "scores",
        "expected_score",
        "expected_status",
        "expected_confidence",
        "positive",
        "negative",
    ),
    GOLDEN_CASES,
    ids=[case[0] for case in GOLDEN_CASES],
)
def test_golden_scenarios_freeze_score_status_and_confidence(
    name: str,
    scores: list[float],
    expected_score: float,
    expected_status: MasteryStatus,
    expected_confidence: MasteryConfidence,
    positive: int,
    negative: int,
) -> None:
    result = compute_mastery(sequence(scores))

    assert result.status is expected_status, name
    assert result.score == pytest.approx(expected_score, abs=1e-12), name
    assert result.confidence is expected_confidence, name
    assert result.evidence_count == len(scores)
    assert result.positive_evidence_count == positive
    assert result.negative_evidence_count == negative


def test_fewer_than_three_evidence_is_not_enough_data_with_empty_score() -> None:
    for scores in ([], [1.0], [1.0, 0.0]):
        result = compute_mastery(sequence(scores))

        assert result.status is MasteryStatus.NOT_ENOUGH_DATA
        assert result.score is None
        assert result.confidence is None
        assert result.confidence_value is None
        assert result.evidence_count == len(scores)
        assert result.last_practiced_at == (
            BASE_TIME + timedelta(hours=len(scores) - 1) if scores else None
        )


def test_status_rules_follow_score_and_confidence_thresholds() -> None:
    # 分数恰为 0.50 不属于 WEAK（规则：小于 0.50 才是）。
    boundary = compute_mastery(sequence([0.5, 0.5, 0.5]))
    assert boundary.status is MasteryStatus.LEARNING
    assert compute_mastery(sequence([0.49, 0.49, 0.49])).status is MasteryStatus.WEAK
    # 低 Confidence 的高分仍保持 LEARNING；5 条起进入 MEDIUM 即可稳定。
    assert compute_mastery(sequence([1.0] * 4)).status is MasteryStatus.LEARNING
    assert compute_mastery(sequence([1.0] * 5)).status is MasteryStatus.STABLE
    assert compute_mastery(sequence([1.0] * 8)).status is MasteryStatus.STABLE
    # 低于 0.80 的高 Confidence 成绩保持 LEARNING（0/1 真实得分下的边界侧）。
    assert compute_mastery(sequence([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])).status is (
        MasteryStatus.LEARNING
    )
    assert compute_mastery(sequence([0.79] * 8)).status is MasteryStatus.LEARNING


def test_confidence_bands_bound_at_effective_counts() -> None:
    cases = {
        1: MasteryConfidence.LOW,
        4: MasteryConfidence.LOW,
        5: MasteryConfidence.MEDIUM,
        7: MasteryConfidence.MEDIUM,
        8: MasteryConfidence.HIGH,
        12: MasteryConfidence.HIGH,
    }
    for count, expected in cases.items():
        result = compute_mastery(sequence([1.0] * count))
        if count < MIN_EVIDENCE_COUNT:
            assert result.confidence is None
        else:
            assert result.confidence is expected, count
    # 分档函数在存储值上回读一致：存储 Confidence → 分档与计算时一致。
    for count in (3, 4, 5, 6, 7, 8, 12):
        result = compute_mastery(sequence([1.0] * count))
        assert result.confidence_value is not None
        assert confidence_level_of(result.confidence_value) is result.confidence


def test_window_keeps_only_latest_twelve_evidence() -> None:
    scores = [0.0] + [1.0] * (WINDOW_SIZE + 2)
    result = compute_mastery(sequence(scores))

    assert result.evidence_count == WINDOW_SIZE
    assert result.score == pytest.approx(1.0, abs=1e-12)
    assert result.positive_evidence_count == WINDOW_SIZE
    assert result.negative_evidence_count == 0


def test_ordering_uses_occurred_at_then_stable_evidence_id() -> None:
    first = evidence(score=1.0, occurred_at=BASE_TIME)
    second = MasteryEvidence(
        evidence_id="a-evidence",
        score=0.0,
        weight=0.9,
        confidence=0.8,
        result="WRONG",
        occurred_at=BASE_TIME,
    )
    duplicate_time = compute_mastery([first, second])
    reversed_input = compute_mastery([second, first])

    assert duplicate_time.score == reversed_input.score


def test_last_verified_at_tracks_latest_positive_result() -> None:
    result = compute_mastery(sequence([1.0, 1.0, 0.0]))

    assert result.last_practiced_at == BASE_TIME + timedelta(hours=2)
    assert result.last_verified_at == BASE_TIME + timedelta(hours=1)

    all_wrong = compute_mastery(sequence([0.0, 0.0, 0.0]))
    assert all_wrong.last_practiced_at == BASE_TIME + timedelta(hours=2)
    assert all_wrong.last_verified_at is None


def test_algorithm_version_is_frozen_identifier() -> None:
    assert ALGORITHM_VERSION == "mastery_v1"


@pytest.mark.anyio
async def test_migration_0025_creates_unique_concept_mastery_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(user_concept_mastery)")
            ).fetchall()
        }
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(user_concept_mastery)")
            ).fetchall()
        }
        foreign_keys = {
            cast(str, row[2])
            for row in await (
                await connection.execute("PRAGMA foreign_key_list(user_concept_mastery)")
            ).fetchall()
        }

    assert version == (25,)
    assert columns == {
        "id",
        "course_id",
        "concept_id",
        "mastery_score",
        "mastery_confidence",
        "evidence_count",
        "positive_evidence_count",
        "negative_evidence_count",
        "last_practiced_at",
        "last_verified_at",
        "algorithm_version",
        "updated_at",
    }
    assert "idx_user_concept_mastery_course" in indexes
    # concept_id 唯一：每 Concept 至多一条快照（内联 UNIQUE 产出 sqlite 自动索引）。
    assert any(index.startswith("sqlite_autoindex_user_concept_mastery") for index in indexes)
    assert {"courses", "concepts"} <= foreign_keys


@pytest.mark.anyio
async def test_concept_mastery_unique_and_score_range_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        now = "2026-09-01T08:00:00.000000Z"
        await connection.execute(
            "INSERT INTO courses (id, name, learning_context, education_stage, depth, "
            "course_type, description, hot_words, status, created_at, updated_at, deleted_at) "
            "VALUES ('course-1', '操作系统', 'SCHOOL', 'UNDERGRADUATE', NULL, NULL, NULL, "
            "'[]', 'ACTIVE', :now, :now, NULL)",
            {"now": now},
        )
        for concept_id, name in [("concept-1", "进程"), ("concept-2", "线程")]:
            await connection.execute(
                "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                "description, concept_type, importance, status, source, created_at, updated_at) "
                "VALUES (:id, 'course-1', :name, :name, '', 'TERM', 3, 'CONFIRMED', "
                "'AI_EXTRACTED', :now, :now)",
                {"id": concept_id, "name": name, "now": now},
            )

        def insert_sql(row_id: str, concept_id: str, score: str) -> str:
            return (
                "INSERT INTO user_concept_mastery "
                "(id, course_id, concept_id, mastery_score, mastery_confidence, "
                "evidence_count, positive_evidence_count, negative_evidence_count, "
                "last_practiced_at, last_verified_at, algorithm_version, updated_at) "
                f"VALUES ('{row_id}', 'course-1', '{concept_id}', {score}, 0.5, "
                "3, 2, 1, NULL, NULL, 'mastery_v1', "
                f"'{now}')"
            )

        await connection.execute(insert_sql("row-1", "concept-1", "0.8"))
        await connection.commit()

        # concept_id 唯一：同概念第二条快照被数据库拒绝。
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(insert_sql("row-2", "concept-1", "0.9"))
        # 分数超出 0~1 被 CHECK 拒绝。
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(insert_sql("row-3", "concept-2", "1.5"))


@pytest.mark.anyio
async def test_http_answer_flows_through_consumer_to_course_mastery(tmp_path: Path) -> None:
    """最高接缝：HTTP 作答 → Consumer 单轮 → HTTP 查询课程 Mastery。"""
    quiz_ids = [f"44444444-4444-4444-8444-44444444444{index}" for index in range(3)]
    async with running_mastery_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course_and_concepts(app)
        for quiz_id in quiz_ids:
            await seed_active_quiz(app, quiz_id=quiz_id, concept_id=CONCEPT_ID)

        for quiz_id in quiz_ids:
            answered = await client.post(
                f"/api/records/{RECORD_ID}/quizzes/{quiz_id}/answers",
                json={"answer": 0},
            )
            assert answered.status_code == 200, answered.text

        processed = await app.state.evidence_consumer.run_once()
        assert processed == 3

        response = await client.get(f"/api/courses/{COURSE_ID}/mastery")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["course_id"] == COURSE_ID
    assert payload["confirmed_concept_count"] == 2
    assert payload["verified_concept_count"] == 1
    assert payload["coverage"] == 0.5
    assert payload["status_counts"] == {
        "not_enough_data": 1,
        "weak": 0,
        "learning": 1,
        "stable": 0,
    }
    # 排序：需关注的状态在前，无证据概念靠后。
    assert [row["concept_id"] for row in payload["concepts"]] == [
        CONCEPT_ID,
        OTHER_CONCEPT_ID,
    ]
    verified = payload["concepts"][0]
    assert verified["status"] == "LEARNING"
    assert verified["mastery_score"] == pytest.approx(1.0, abs=1e-12)
    assert verified["confidence"] == "LOW"
    assert verified["evidence_count"] == 3
    assert verified["positive_evidence_count"] == 3
    assert verified["negative_evidence_count"] == 0
    assert verified["last_practiced_at"] is not None
    assert verified["last_verified_at"] is not None
    empty = payload["concepts"][1]
    assert empty["status"] == "NOT_ENOUGH_DATA"
    assert empty["mastery_score"] is None
    assert empty["confidence"] is None
    assert empty["evidence_count"] == 0
    assert "average" not in payload


@pytest.mark.anyio
async def test_course_mastery_status_filter_returns_only_matching_concepts(
    tmp_path: Path,
) -> None:
    quiz_ids = [f"44444444-4444-4444-8444-44444444444{index}" for index in range(3)]
    async with running_mastery_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course_and_concepts(app)
        for quiz_id in quiz_ids:
            await seed_active_quiz(app, quiz_id=quiz_id, concept_id=CONCEPT_ID)
            await client.post(
                f"/api/records/{RECORD_ID}/quizzes/{quiz_id}/answers",
                json={"answer": 0},
            )
        await app.state.evidence_consumer.run_once()

        learning_only = await client.get(
            f"/api/courses/{COURSE_ID}/mastery", params={"status": "LEARNING"}
        )
        weak_only = await client.get(f"/api/courses/{COURSE_ID}/mastery", params={"status": "WEAK"})

    assert [row["concept_id"] for row in learning_only.json()["concepts"]] == [CONCEPT_ID]
    # 筛选只影响列表，分布仍反映全量（另一概念无证据）。
    assert learning_only.json()["status_counts"]["not_enough_data"] == 1
    assert weak_only.json()["concepts"] == []


@pytest.mark.anyio
async def test_course_mastery_excludes_archived_concepts_and_unknown_course(
    tmp_path: Path,
) -> None:
    async with running_mastery_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course_and_concepts(
            app,
            concepts=[
                (CONCEPT_ID, "进程调度", "CONFIRMED"),
                (ARCHIVED_CONCEPT_ID, "已归档概念", "ARCHIVED"),
            ],
        )

        response = await client.get(f"/api/courses/{COURSE_ID}/mastery")
        missing = await client.get("/api/courses/99999999-9999-4999-8999-999999999999/mastery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmed_concept_count"] == 1
    assert [row["concept_id"] for row in payload["concepts"]] == [CONCEPT_ID]
    assert missing.status_code == 404
    assert missing.json()["code"] == "COURSE_NOT_FOUND"


@pytest.mark.anyio
async def test_mastery_only_consumes_scored_quiz_evidence_of_live_records(
    tmp_path: Path,
) -> None:
    """有效集合过滤：非 QUIZ、无分数、无归属与已删除 Record 都不参与计算。"""
    async with running_mastery_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course_and_concepts(app)
        await seed_active_quiz(
            app, quiz_id="44444444-4444-4444-8444-444444444440", concept_id=CONCEPT_ID
        )
        await client.post(
            f"/api/records/{RECORD_ID}/quizzes/44444444-4444-4444-8444-444444444440/answers",
            json={"answer": 0},
        )
        async with app.state.session_factory() as session, session.begin():
            # 非 QUIZ 证据（用户确认活动）带 Concept 也不抬高掌握度。
            await session.execute(
                text(
                    "INSERT INTO learning_events (id, course_id, record_id, concept_id, "
                    "event_type, source_type, source_id, result, score, difficulty, duration_ms, "
                    "metadata_json, idempotency_key, schema_version, occurred_at, created_at) "
                    "VALUES ('event-summary-1', :course_id, :record_id, :concept_id, "
                    "'SUMMARY_CONFIRMED', 'TEST_SOURCE', 'summary-1', NULL, NULL, NULL, NULL, "
                    "'{}', 'summary-confirmed:1', 1, :now, :now)"
                ),
                {
                    "course_id": COURSE_ID,
                    "record_id": RECORD_ID,
                    "concept_id": CONCEPT_ID,
                    "now": NOW,
                },
            )
            # 无分数 QUIZ 与无归属 QUIZ：均不参与。
            for suffix, concept_id, score in [
                ("missing-score", CONCEPT_ID, None),
                ("missing-concept", None, 1.0),
            ]:
                await session.execute(
                    text(
                        "INSERT INTO learning_events (id, course_id, record_id, concept_id, "
                        "event_type, source_type, source_id, result, score, difficulty, "
                        "duration_ms, metadata_json, idempotency_key, schema_version, "
                        "occurred_at, created_at) "
                        "VALUES (:event_id, :course_id, :record_id, :concept_id, 'QUIZ_ANSWERED', "
                        "'TEST_SOURCE', :event_id, 'CORRECT', :score, 'EASY', NULL, '{}', "
                        ":event_id, 1, :now, :now)"
                    ),
                    {
                        "event_id": f"event-{suffix}",
                        "course_id": COURSE_ID,
                        "record_id": RECORD_ID,
                        "concept_id": concept_id,
                        "score": score,
                        "now": NOW,
                    },
                )
        await app.state.evidence_consumer.run_once()

        before_delete = await client.get(f"/api/courses/{COURSE_ID}/mastery")
        async with app.state.session_factory() as session:
            await session.execute(
                text("UPDATE records SET deleted_at = :now WHERE id = :record_id"),
                {"now": NOW, "record_id": RECORD_ID},
            )
            await session.commit()
        await MasteryService.recompute_concepts(
            app.state.session_factory, [CONCEPT_ID, OTHER_CONCEPT_ID]
        )
        response = await client.get(f"/api/courses/{COURSE_ID}/mastery")

    # 只有带分数、带归属的 QUIZ 参与：非 QUIZ / 无分数 / 无归属均被排除。
    before_payload = before_delete.json()
    before_row = next(row for row in before_payload["concepts"] if row["concept_id"] == CONCEPT_ID)
    assert before_payload["verified_concept_count"] == 1
    assert before_row["evidence_count"] == 1
    row = next(row for row in response.json()["concepts"] if row["concept_id"] == CONCEPT_ID)
    assert row["evidence_count"] == 0
    assert row["mastery_score"] is None
    assert row["status"] == "NOT_ENOUGH_DATA"


@pytest.mark.anyio
async def test_mastery_recompute_is_idempotent_across_rounds(tmp_path: Path) -> None:
    async with running_mastery_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course_and_concepts(app)
        await seed_active_quiz(
            app, quiz_id="44444444-4444-4444-8444-444444444440", concept_id=CONCEPT_ID
        )
        await client.post(
            f"/api/records/{RECORD_ID}/quizzes/44444444-4444-4444-8444-444444444440/answers",
            json={"answer": 0},
        )
        await app.state.evidence_consumer.run_once()
        async with app.state.session_factory() as session:
            first = dict(
                (
                    await session.execute(
                        text(
                            "SELECT id, evidence_count, mastery_score, algorithm_version, "
                            "updated_at FROM user_concept_mastery WHERE concept_id = :concept_id"
                        ),
                        {"concept_id": CONCEPT_ID},
                    )
                )
                .mappings()
                .one()
            )

        # 重复重建（fresh consumer 全量重扫 + 显式重算）不产生第二条快照、不重复计数。
        restarted = EvidenceConsumer(app.state.session_factory)
        await restarted.run_once()
        await MasteryService.recompute_concepts(app.state.session_factory, [CONCEPT_ID])
        async with app.state.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id, evidence_count, mastery_score, algorithm_version, "
                            "updated_at FROM user_concept_mastery WHERE concept_id = :concept_id"
                        ),
                        {"concept_id": CONCEPT_ID},
                    )
                )
                .mappings()
                .all()
            )

    assert len(rows) == 1
    assert first["evidence_count"] == 1
    assert dict(rows[0])["evidence_count"] == 1
    assert dict(rows[0])["algorithm_version"] == ALGORITHM_VERSION
