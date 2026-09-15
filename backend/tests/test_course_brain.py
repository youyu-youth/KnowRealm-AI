"""迁移 0023：Course Brain 三表（concepts / concept_relations / record_concepts）
与 source_anchor_links 的 CONCEPT 值域扩展：schema、约束行为与升级路径。

迁移口径对齐 test_source_anchors 动态惯例：手工执行 migrations[:-1] 构造升级库，
run_migrations 补齐后与全新库双口径对照；锚点链接表重建后既有行必须完好。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from app.db.migrations import MIGRATIONS_DIR, run_migrations, supported_user_version

COURSE_ID = "c1000000-0000-4000-8000-000000000001"
OTHER_COURSE_ID = "c1000000-0000-4000-8000-000000000002"
RECORD_ID = "c1000000-0000-4000-8000-000000000003"
KP_ID = "c1000000-0000-4000-8000-000000000004"
ANCHOR_ID = "c1000000-0000-4000-8000-000000000005"

PARENT_ROWS_SQL = (
    "INSERT INTO courses (id, name, learning_context, depth, status, created_at, updated_at) "
    f"VALUES ('{COURSE_ID}', '测试课程', 'INTEREST', 'BEGINNER', 'ACTIVE', "
    "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z');\n"
    "INSERT INTO courses (id, name, learning_context, depth, status, created_at, updated_at) "
    f"VALUES ('{OTHER_COURSE_ID}', '另一课程', 'INTEREST', 'BEGINNER', 'ACTIVE', "
    "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z');\n"
    "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
    "created_at, updated_at) "
    f"VALUES ('{RECORD_ID}', '{COURSE_ID}', 'RECORDING', '测试记录', 'NOTE', 0, "
    "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z');\n"
    "INSERT INTO knowledge_points (id, record_id, name, detail, tags, importance, "
    "generation_status, created_at, updated_at) "
    f"VALUES ('{KP_ID}', '{RECORD_ID}', '知识点', '细节', '[]', 3, 'ACTIVE', "
    "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z');\n"
    "INSERT INTO source_anchors (id, course_id, source_type, source_id, record_id) "
    f"VALUES ('{ANCHOR_ID}', '{COURSE_ID}', 'USER_NOTE', 'note-1', '{RECORD_ID}');"
)


async def _columns(connection: aiosqlite.Connection, table: str) -> dict[str, int]:
    rows = await (await connection.execute(f"PRAGMA table_info({table})")).fetchall()
    return {row[1]: int(row[3]) for row in rows}


async def _foreign_keys(connection: aiosqlite.Connection, table: str) -> list[tuple[str, str, str]]:
    rows = await (await connection.execute(f"PRAGMA foreign_key_list({table})")).fetchall()
    return sorted((row[2], row[3], row[6]) for row in rows)


async def _index_names(connection: aiosqlite.Connection, table: str) -> set[str]:
    rows = await (await connection.execute(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


async def assert_course_brain_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        concept_columns = await _columns(connection, "concepts")
        relation_columns = await _columns(connection, "concept_relations")
        record_concept_columns = await _columns(connection, "record_concepts")
        concept_fks = await _foreign_keys(connection, "concepts")
        relation_fks = await _foreign_keys(connection, "concept_relations")
        record_concept_fks = await _foreign_keys(connection, "record_concepts")
        concept_indexes = await (await connection.execute("PRAGMA index_list(concepts)")).fetchall()
        relation_indexes = await _index_names(connection, "concept_relations")
        record_concept_indexes = await _index_names(connection, "record_concepts")
        link_sql = await (
            await connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'source_anchor_links'"
            )
        ).fetchone()

    assert version == (supported_user_version(),)

    assert list(concept_columns) == [
        "id",
        "course_id",
        "canonical_name",
        "normalized_name",
        "description",
        "concept_type",
        "importance",
        "status",
        "source",
        "created_at",
        "updated_at",
    ]
    # id 为 TEXT PRIMARY KEY（SQLite notnull 位恒 0）；其余列全 NOT NULL。
    assert all(concept_columns[column] == 1 for column in concept_columns if column != "id")
    assert "deleted_at" not in concept_columns, "ARCHIVED 即退役语义，不允许软删列"

    assert list(relation_columns) == [
        "id",
        "course_id",
        "source_concept_id",
        "target_concept_id",
        "relation_type",
        "confidence",
        "evidence_count",
        "status",
        "created_at",
        "updated_at",
    ]
    assert list(record_concept_columns) == [
        "id",
        "record_id",
        "concept_id",
        "knowledge_point_id",
        "relevance",
        "evidence_count",
        "first_start_ms",
        "created_at",
        "updated_at",
    ]
    assert record_concept_columns["knowledge_point_id"] == 0
    assert record_concept_columns["first_start_ms"] == 0

    assert concept_fks == [("courses", "course_id", "CASCADE")]
    assert relation_fks == [
        ("concepts", "source_concept_id", "CASCADE"),
        ("concepts", "target_concept_id", "CASCADE"),
        ("courses", "course_id", "CASCADE"),
    ]
    assert record_concept_fks == [
        ("concepts", "concept_id", "CASCADE"),
        ("knowledge_points", "knowledge_point_id", "SET NULL"),
        ("records", "record_id", "CASCADE"),
    ]

    confirmed_index = next(
        (row for row in concept_indexes if row[1] == "idx_concepts_course_confirmed"), None
    )
    assert confirmed_index is not None
    assert int(confirmed_index[2]) == 1, "idx_concepts_course_confirmed 必须唯一"
    assert int(confirmed_index[4]) == 1, "idx_concepts_course_confirmed 必须是部分索引"
    index_sql_row = await _read_index_sql(db_path, "idx_concepts_course_confirmed")
    assert "WHERE status = 'CONFIRMED'" in index_sql_row
    assert "idx_concepts_course_status" in {row[1] for row in concept_indexes}
    assert relation_indexes >= {"idx_concept_relations_course_status"}
    assert record_concept_indexes >= {"idx_record_concepts_concept", "idx_record_concepts_record"}
    assert link_sql is not None and "'CONCEPT'" in str(link_sql[0])


async def _read_index_sql(db_path: Path, index_name: str) -> str:
    async with aiosqlite.connect(db_path) as connection:
        row = await (
            await connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = :name",
                {"name": index_name},
            )
        ).fetchone()
    return "" if row is None else str(row[0])


@asynccontextmanager
async def upgrade_v22_database(db_path: Path) -> AsyncGenerator[Path]:
    """手工执行 migrations[:-1] 构造前一版本库，插入存量数据后升级。"""
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with aiosqlite.connect(db_path) as connection:
        # 对齐 run_migrations：重放期间 FK 关闭（否则 rename 会改写其他表 FK 文本）。
        await connection.execute("PRAGMA foreign_keys=OFF")
        for path in migrations[:-1]:
            await connection.executescript(path.read_text(encoding="utf-8"))
        await connection.execute(f"PRAGMA user_version={len(migrations) - 1}")
        await connection.executescript(PARENT_ROWS_SQL)
        await connection.execute(
            "INSERT INTO source_anchor_links (id, resource_type, resource_id, "
            "source_anchor_id, relation_type) "
            f"VALUES ('legacy-link', 'SUMMARY', 'summary-1', '{ANCHOR_ID}', 'SUPPORTS')"
        )
        await connection.commit()
    await run_migrations(db_path)
    yield db_path


@pytest.mark.anyio
async def test_migration_0023_creates_course_brain_tables_on_fresh_and_upgraded_databases(
    tmp_path: Path,
) -> None:
    fresh_db = tmp_path / "fresh.db"
    upgraded_db = tmp_path / "upgraded.db"

    await run_migrations(fresh_db)
    async with upgrade_v22_database(upgraded_db):
        pass

    await assert_course_brain_schema(fresh_db)
    await assert_course_brain_schema(upgraded_db)


@pytest.mark.anyio
async def test_source_anchor_links_rebuild_preserves_rows_and_accepts_concept(
    tmp_path: Path,
) -> None:
    async with upgrade_v22_database(tmp_path / "upgraded.db") as db_path:
        async with aiosqlite.connect(db_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            legacy = await (
                await connection.execute(
                    "SELECT resource_type, resource_id, source_anchor_id FROM "
                    "source_anchor_links WHERE id = 'legacy-link'"
                )
            ).fetchone()
            await connection.execute(
                "INSERT INTO source_anchor_links (id, resource_type, resource_id, "
                "source_anchor_id, relation_type) "
                f"VALUES ('concept-link', 'CONCEPT', 'concept-1', '{ANCHOR_ID}', 'PRIMARY')"
            )
            await connection.commit()

    assert legacy == ("SUMMARY", "summary-1", ANCHOR_ID)


@pytest.mark.anyio
async def test_concepts_confirmed_normalized_name_unique_per_course(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    insert = (
        "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
        "description, concept_type, importance, status, source, created_at, updated_at) "
        "VALUES (:id, :course_id, :name, :normalized, '', 'TERM', 3, :status, "
        "'AI_EXTRACTED', '2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z')"
    )
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.executescript(PARENT_ROWS_SQL)
        # 候选/归档阶段允许同名——Resolution 审核时收敛。
        await connection.execute(
            insert,
            {
                "id": "candidate-1",
                "course_id": COURSE_ID,
                "name": "MVCC",
                "normalized": "mvcc",
                "status": "CANDIDATE",
            },
        )
        await connection.execute(
            insert,
            {
                "id": "candidate-2",
                "course_id": COURSE_ID,
                "name": "MVCC",
                "normalized": "mvcc",
                "status": "CANDIDATE",
            },
        )
        await connection.execute(
            insert,
            {
                "id": "confirmed-1",
                "course_id": COURSE_ID,
                "name": "MVCC",
                "normalized": "mvcc",
                "status": "CONFIRMED",
            },
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "confirmed-dup",
                    "course_id": COURSE_ID,
                    "name": "mvcc",
                    "normalized": "mvcc",
                    "status": "CONFIRMED",
                },
            )
        await connection.execute(
            insert,
            {
                "id": "archived-dup",
                "course_id": COURSE_ID,
                "name": "mvcc",
                "normalized": "mvcc",
                "status": "ARCHIVED",
            },
        )
        # 跨课程同名不冲突（唯一域是课程内）。
        await connection.execute(
            insert,
            {
                "id": "confirmed-other-course",
                "course_id": OTHER_COURSE_ID,
                "name": "MVCC",
                "normalized": "mvcc",
                "status": "CONFIRMED",
            },
        )
        await connection.commit()


@pytest.mark.anyio
async def test_concepts_reject_invalid_status_source_and_importance(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    insert = (
        "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
        "description, concept_type, importance, status, source, created_at, updated_at) "
        "VALUES (:id, :course_id, 'MVCC', 'mvcc', '', 'TERM', :importance, :status, :source, "
        "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z')"
    )
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        for payload in (
            {"id": "bad-status", "importance": 3, "status": "DRAFT", "source": "AI_EXTRACTED"},
            {"id": "bad-source", "importance": 3, "status": "CANDIDATE", "source": "UNKNOWN"},
            {
                "id": "bad-importance-low",
                "importance": 0,
                "status": "CANDIDATE",
                "source": "SYSTEM",
            },
            {
                "id": "bad-importance-high",
                "importance": 6,
                "status": "CANDIDATE",
                "source": "SYSTEM",
            },
        ):
            with pytest.raises(aiosqlite.IntegrityError):
                await connection.execute(insert, {"course_id": COURSE_ID, **payload})


@pytest.mark.anyio
async def test_concept_relations_reject_self_loop_and_duplicate_triple(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    insert = (
        "INSERT INTO concept_relations (id, course_id, source_concept_id, target_concept_id, "
        "relation_type, confidence, evidence_count, status, created_at, updated_at) "
        "VALUES (:id, :course_id, :source_id, :target_id, 'PREREQUISITE', 0.5, 1, :status, "
        "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z')"
    )
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        for concept_id, name in (("concept-a", "A"), ("concept-b", "B")):
            await connection.execute(
                "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                "description, concept_type, importance, status, source, created_at, updated_at) "
                f"VALUES ('{concept_id}', '{COURSE_ID}', '{name}', '{name.lower()}', '', 'TERM', "
                "3, 'CONFIRMED', 'USER_CONFIRMED', '2026-09-15T00:00:00.000000Z', "
                "'2026-09-15T00:00:00.000000Z')"
            )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "self-loop",
                    "course_id": COURSE_ID,
                    "source_id": "concept-a",
                    "target_id": "concept-a",
                    "status": "CANDIDATE",
                },
            )
        await connection.execute(
            insert,
            {
                "id": "relation-1",
                "course_id": COURSE_ID,
                "source_id": "concept-a",
                "target_id": "concept-b",
                "status": "CANDIDATE",
            },
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "relation-dup",
                    "course_id": COURSE_ID,
                    "source_id": "concept-a",
                    "target_id": "concept-b",
                    "status": "CONFIRMED",
                },
            )
        # 反向关系是不同四元组，允许共存（有向图）。
        await connection.execute(
            insert,
            {
                "id": "relation-reverse",
                "course_id": COURSE_ID,
                "source_id": "concept-b",
                "target_id": "concept-a",
                "status": "CANDIDATE",
            },
        )
        await connection.commit()


@pytest.mark.anyio
async def test_record_concepts_unique_pair_and_kp_bridge_set_null(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.executescript(PARENT_ROWS_SQL)
        await connection.execute(
            "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
            "description, concept_type, importance, status, source, created_at, updated_at) "
            f"VALUES ('concept-a', '{COURSE_ID}', 'A', 'a', '', 'TERM', 3, 'CONFIRMED', "
            "'USER_CONFIRMED', '2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z')"
        )
        insert = (
            "INSERT INTO record_concepts (id, record_id, concept_id, knowledge_point_id, "
            "relevance, evidence_count, first_start_ms, created_at, updated_at) "
            "VALUES (:id, :record_id, :concept_id, :kp_id, 0.8, 2, 1200, "
            "'2026-09-15T00:00:00.000000Z', '2026-09-15T00:00:00.000000Z')"
        )
        await connection.execute(
            insert,
            {
                "id": "rc-1",
                "record_id": RECORD_ID,
                "concept_id": "concept-a",
                "kp_id": KP_ID,
            },
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "rc-dup",
                    "record_id": RECORD_ID,
                    "concept_id": "concept-a",
                    "kp_id": None,
                },
            )
        await connection.execute(f"DELETE FROM knowledge_points WHERE id = '{KP_ID}'")
        row = await (
            await connection.execute(
                "SELECT knowledge_point_id FROM record_concepts WHERE id = 'rc-1'"
            )
        ).fetchone()
        await connection.commit()

    assert row == (None,)
