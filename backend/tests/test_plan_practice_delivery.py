"""计划闭环交付：生产导出恢复、五题型固定依据及真实墓碑清理。"""

import json
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import aiosqlite
import pytest
from sqlalchemy import func, select

from app.db.base import utcnow
from app.db.engine import create_database
from app.db.migrations import supported_user_version
from app.modules.capture.models import RecordFile
from app.modules.course.models import Course
from app.modules.course.tombstone_cleanup import DocumentCleanupService
from app.modules.data.archive import create_rolling_backup, restore_archive
from app.modules.quiz.models import Quiz, QuizTestItem
from app.modules.record.models import LearningEvent, Record
from tests.test_agent_runs import apply_migrations_upto
from tests.test_plan_editing import (
    COURSE_ID,
    ITEM_ID,
    RECORD_ID,
    seed_course,
    seed_goal,
    seed_item,
    seed_plan,
    seed_record,
)
from tests.test_practice_preparation import (
    BASE,
    add_questions,
    configure,
    save,
    seed,
    start,
    terminal,
)
from tests.test_practice_round import (
    GradingModel,
    answer_all,
    begin,
    practice_app,
    ready_fifteen,
    wait_status,
)


@pytest.mark.anyio
async def test_pre_feature_database_upgrades_and_old_study_item_can_start(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    db_path = data_dir / "knowrealm.db"
    await apply_migrations_upto(db_path, 51)
    engine, factory = create_database(db_path)
    try:
        await seed_course(factory)
        await seed_goal(factory)
        await seed_record(factory)
        await seed_plan(factory)
        await seed_item(factory, ITEM_ID)
    finally:
        await engine.dispose()
    async with practice_app(tmp_path, GradingModel(0)) as (client, _factory):
        base = f"/api/plan-items/{ITEM_ID}/study"
        state = (await client.get(base)).json()
        assert state["source_status"] == "MISSING"
        assert state["tab"] == "summary" and state["visit_id"] is None
        bound = await client.patch(
            f"/api/courses/{COURSE_ID}/plans/{state['plan_id']}/items/{ITEM_ID}",
            json={"record_id": RECORD_ID},
        )
        assert bound.status_code == 200, bound.text
        started = await client.post(
            base + "/start", json={"request_id": str(uuid4()), "record_id": RECORD_ID}
        )
        assert started.status_code == 200, started.text
        assert started.json()["source"]["record_id"] == RECORD_ID
        async with aiosqlite.connect(db_path) as connection:
            assert (await (await connection.execute("PRAGMA user_version")).fetchone()) == (
                supported_user_version(),
            )
            assert await (await connection.execute("PRAGMA foreign_key_check")).fetchall() == []
    snapshots = list((data_dir / "backups").glob("knowrealm-premigrate-*.db"))
    assert len(snapshots) == 1
    async with aiosqlite.connect(snapshots[0]) as connection:
        assert (await (await connection.execute("PRAGMA user_version")).fetchone()) == (51,)
        assert (
            await (await connection.execute("SELECT count(*) FROM learning_plan_items")).fetchone()
        ) == (1,)


@pytest.mark.anyio
async def test_five_types_resume_after_export_restore_and_directory_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "original"
    answers: dict[str, int | str | list[int] | list[str]] = {
        "MULTIPLE_CHOICE": 0,
        "MULTIPLE_SELECT": [0, 1],
        "TRUE_FALSE": 0,
        "FILL_BLANK": ["Redis"],
        "SHORT_ANSWER": "我的简答作答",
    }
    correct = {**answers, "FILL_BLANK": [["Redis"]], "SHORT_ANSWER": "秘密参考答案"}
    async with practice_app(original, GradingModel(0)) as (client, factory):
        await seed(factory)
        configure(original, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        async with factory() as session, session.begin():
            quizzes = list(await session.scalars(select(Quiz).order_by(Quiz.stem)))
            for index, quiz in enumerate(quizzes):
                quiz.question_type = list(answers)[index % 5]
                if quiz.question_type == "FILL_BLANK":
                    quiz.stem += " ____"
                quiz.options_json = json.dumps(["Redis", "内存", "磁盘"])
                quiz.correct_answer_json = json.dumps(correct[quiz.question_type])
        await save(client, [RECORD_ID], question_types=list(answers))
        await start(client, 1)
        assert (await terminal(client))["outcome"] == "READY"
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        for item in paper["items"][:6]:
            response = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": item["id"], "answer": answers[item["question_type"]]},
            )
            assert response.status_code == 200, response.text
        async with factory() as session:
            frozen = dict(
                (await session.execute(select(QuizTestItem.id, QuizTestItem.frozen_json))).all()
            )
        exported = await client.post(
            "/api/settings/data-directory/export", json={"include_secrets": False}
        )
        assert exported.status_code == 200, exported.text
        archive = original / "KnowRealm" / "exports" / exported.json()["file_name"]
        with ZipFile(archive) as package:
            assert "config/providers.json" not in package.namelist()
        # 独立目录避开启动时已生成的当日备份，不改变每日仅备份一次的契约。
        backup = await create_rolling_backup(
            original / "KnowRealm" / "knowrealm.db", tmp_path / "fresh-backups"
        )
        async with aiosqlite.connect(backup) as connection:
            assert (await (await connection.execute("PRAGMA integrity_check")).fetchone()) == (
                "ok",
            )
            assert {
                row[0]: row[1]
                for row in await (
                    await connection.execute("SELECT id, frozen_json FROM quiz_test_items")
                ).fetchall()
            } == frozen
            assert (
                await (
                    await connection.execute(
                        "SELECT count(*) FROM quiz_test_items WHERE answered_at IS NOT NULL"
                    )
                ).fetchone()
            ) == (6,)
    restored = tmp_path / "restored"
    await restore_archive(restored / "KnowRealm", archive)
    moved = tmp_path / "moved"
    restored.rename(moved)
    model = GradingModel(3)
    async with practice_app(moved, model) as (client, factory):
        configure(moved, monkeypatch)
        state = (await client.get(BASE)).json()
        assert state["requirements"]["revision"] == 1
        assert (state["round"]["test_id"], state["round"]["answered_count"]) == (test_id, 6)
        assert (await begin(client, 1)).json()["test_id"] == test_id
        resumed = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert [item["stem"] for item in resumed["items"]] == [
            item["stem"] for item in paper["items"]
        ]
        assert [item["user_answer"] for item in resumed["items"][:6]] == [
            answers[item["question_type"]] for item in resumed["items"][:6]
        ]
        assert all(item["correct_answer"] is None for item in resumed["items"])
        async with factory() as session:
            assert (
                dict(
                    (await session.execute(select(QuizTestItem.id, QuizTestItem.frozen_json))).all()
                )
                == frozen
            )
        for item in resumed["items"][6:]:
            response = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": item["id"], "answer": answers[item["question_type"]]},
            )
            assert response.status_code == 200, response.text
        assert (await client.post(f"/api/quiz-tests/{test_id}/submit")).status_code == 200
        done = await wait_status(client, test_id, ("COMPLETED", "GRADING_FAILED"))
        assert done["status"] == "COMPLETED"
        assert [item["score"] for item in done["items"]].count(1.0) == 12
        assert [item["score"] for item in done["items"]].count(0.5) == 3
        assert done["score"] == 0.9
        assert model.calls == 3
        assert (await client.get(BASE)).json()["round"]["grading_complete"] is True
        async with factory() as session:
            events = list(await session.scalars(select(LearningEvent)))
            assert len([event for event in events if event.event_type == "QUIZ_ANSWERED"]) == 15
            assert (
                len([event for event in events if event.event_type == "QUIZ_TEST_COMPLETED"]) == 1
            )
            assert len(events) == len({event.idempotency_key for event in events})


@pytest.mark.anyio
@pytest.mark.parametrize("delete_course", [False, True])
async def test_production_cleanup_with_plan_practice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delete_course: bool
) -> None:
    async with practice_app(tmp_path, GradingModel(15)) as (client, factory):
        await seed(factory)
        source_file = tmp_path / "KnowRealm" / "files" / RECORD_ID / "source.txt"
        source_file.parent.mkdir(parents=True)
        source_file.write_bytes(b"Redis delivery fixture")
        async with factory() as session, session.begin():
            session.add(
                RecordFile(
                    record_id=RECORD_ID,
                    file_type="DOCUMENT",
                    source_type="UPLOADED",
                    file_path=f"files/{RECORD_ID}/source.txt",
                    original_name="source.txt",
                    mime_type="text/plain",
                    file_size=source_file.stat().st_size,
                    sequence_no=1,
                    content_hash=sha256(source_file.read_bytes()).hexdigest(),
                )
            )
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper, upto=6)
        if not delete_course:
            target = await client.post(
                "/api/courses",
                json={"name": "资料移入课程", "learning_context": "INTEREST", "depth": "BEGINNER"},
            )
            assert target.status_code == 201, target.text
            moved = await client.patch(
                f"/api/records/{RECORD_ID}/course",
                json={"target_course_id": target.json()["id"]},
            )
            assert moved.status_code == 200, moved.text
            moved_paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
            assert [item["stem"] for item in moved_paper["items"]] == [
                item["stem"] for item in paper["items"]
            ]
            assert all(item["source_valid"] is False for item in moved_paper["items"])
            assert source_file.is_file()
        endpoint = f"/api/courses/{COURSE_ID}" if delete_course else f"/api/records/{RECORD_ID}"
        deleted = await client.delete(endpoint)
        assert deleted.status_code == 204, deleted.text
        if delete_course:
            assert (await client.get(BASE)).status_code == 404
            assert (await client.get(f"/api/quiz-tests/{test_id}")).status_code == 404
        await DocumentCleanupService.purge_expired(
            factory, tmp_path / "KnowRealm", now=utcnow() + timedelta(days=31)
        )
        async with factory() as session:
            assert await session.get(Record, RECORD_ID) is None
            assert await session.scalar(select(func.count()).select_from(Quiz)) == 0
            assert await session.scalar(select(func.count()).select_from(RecordFile)) == 0
        assert not source_file.parent.exists()
        if delete_course:
            assert (await client.get(f"/api/courses/{COURSE_ID}")).status_code == 404
            async with factory() as session:
                assert await session.get(Course, COURSE_ID) is None
                assert await session.scalar(select(func.count()).select_from(QuizTestItem)) == 0
        else:
            survived = (await client.get(f"/api/quiz-tests/{test_id}")).json()
            assert len(survived["items"]) == 15
            assert [item["stem"] for item in survived["items"]] == [
                item["stem"] for item in paper["items"]
            ]
            assert all(item["source_valid"] is False for item in survived["items"])
            async with factory() as session:
                assert all(
                    item.quiz_id is None for item in await session.scalars(select(QuizTestItem))
                )
            await answer_all(client, survived)
            assert (await client.post(f"/api/quiz-tests/{test_id}/submit")).status_code == 200
            done = await wait_status(client, test_id, ("COMPLETED", "GRADING_FAILED"))
            assert done["status"] == "COMPLETED" and done["score"] == 0.5
