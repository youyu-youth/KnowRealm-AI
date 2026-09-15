"""Course Brain：迁移 0023 三表结构与约束（CB-02）+ 查询模块（CB-03）。

迁移口径对齐 test_source_anchors 动态惯例：手工执行 migrations[:-1] 构造升级库，
run_migrations 补齐后与全新库双口径对照；锚点链接表重建后既有行必须完好。
查询口径：六态派生、CONFIRMED-only 不泄漏、来源回溯与 B2 检索扩展。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import MIGRATIONS_DIR, run_migrations, supported_user_version
from app.main import create_app
from app.modules.course_brain.schemas import CourseBrainSearchOut
from app.modules.course_brain.service import CourseBrainService, normalize_concept_name
from app.modules.course_brain.worker import course_brain_spec, preflight
from app.modules.llm.service import StructuredGenerationError, StructuredModelResult
from app.modules.search.segment_service import (
    ENTITY_CONCEPT,
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.search.tokenizer import tokenize
from app.modules.settings.config import (
    grant_llm_consent as grant_llm_consent_file,
)
from app.modules.settings.config import (
    save_llm_provider,
)
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-15T08:00:00.000000Z"

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


# ---------------------------------------------------------------------------
# CB-03 查询模块：快照六态 / 概念视图 / 来源回溯 / 检索增强 / 手动创建
# ---------------------------------------------------------------------------


@asynccontextmanager
async def running_brain_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
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
    *,
    status: str = "ACTIVE",
    deleted_at: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, status, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, '测试课程', 'INTEREST', 'BEGINNER', :status, :now, :now, :deleted_at)"
            ),
            {"id": course_id, "status": status, "now": NOW, "deleted_at": deleted_at},
        )


async def seed_record(
    app: FastAPI,
    record_id: str,
    course_id: str,
    *,
    title: str = "测试记录",
    deleted_at: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'RECORDING', :title, 'COMPLETED', 60000, "
                ":now, :now, :deleted_at)"
            ),
            {
                "id": record_id,
                "course_id": course_id,
                "title": title,
                "now": NOW,
                "deleted_at": deleted_at,
            },
        )


async def seed_transcript_segment(
    app: FastAPI,
    *,
    record_id: str,
    segment_id: str,
    transcript_id: str,
    file_id: str,
    content: str,
    sequence_no: int = 0,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
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
        await session.execute(
            text(
                "INSERT INTO transcripts (id, record_id, language, content, source_version, "
                "edited_by_user, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', :content, 1, 0, :now, :now, NULL)"
            ),
            {"id": transcript_id, "record_id": record_id, "content": content, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                "speaker, content, content_hash) "
                "VALUES (:id, :transcript_id, :record_id, :file_id, :sequence_no, "
                ":start_ms, :end_ms, :start_ms, :end_ms, NULL, :content, :content_hash)"
            ),
            {
                "id": segment_id,
                "transcript_id": transcript_id,
                "record_id": record_id,
                "file_id": file_id,
                "sequence_no": sequence_no,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "content": content,
                "content_hash": content_hash(content),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, [segment_id]
        )


async def seed_extra_transcript_segment(
    app: FastAPI,
    *,
    record_id: str,
    segment_id: str,
    transcript_id: str,
    file_id: str,
    content: str,
    sequence_no: int,
) -> None:
    """复用已存在的 transcript/record_file 追加分片并同步索引。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
                "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
                "speaker, content, content_hash) "
                "VALUES (:id, :transcript_id, :record_id, :file_id, :sequence_no, "
                "NULL, NULL, NULL, NULL, NULL, :content, :content_hash)"
            ),
            {
                "id": segment_id,
                "transcript_id": transcript_id,
                "record_id": record_id,
                "file_id": file_id,
                "sequence_no": sequence_no,
                "content": content,
                "content_hash": content_hash(content),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, [segment_id]
        )


async def seed_knowledge_point(
    app: FastAPI,
    *,
    kp_id: str,
    record_id: str,
    name: str = "知识点",
    status: str = "ACTIVE",
    deleted_at: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO knowledge_points (id, record_id, name, detail, tags, importance, "
                "generation_status, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, :name, '细节', '[]', 3, :status, "
                ":now, :now, :deleted_at)"
            ),
            {
                "id": kp_id,
                "record_id": record_id,
                "name": name,
                "status": status,
                "now": NOW,
                "deleted_at": deleted_at,
            },
        )


async def seed_concept(
    app: FastAPI,
    *,
    concept_id: str,
    course_id: str,
    name: str,
    status: str = "CONFIRMED",
    source: str = "AI_EXTRACTED",
    description: str = "",
    importance: int = 3,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                "description, concept_type, importance, status, source, created_at, updated_at) "
                "VALUES (:id, :course_id, :name, :normalized, :description, 'TERM', :importance, "
                ":status, :source, :now, :now)"
            ),
            {
                "id": concept_id,
                "course_id": course_id,
                "name": name,
                "normalized": normalize_concept_name(name),
                "description": description,
                "importance": importance,
                "status": status,
                "source": source,
                "now": NOW,
            },
        )
    await index_concept(app, concept_id)


async def index_concept(app: FastAPI, concept_id: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await SegmentSearchService.upsert_segment_index(session, ENTITY_CONCEPT, [concept_id])


async def force_index_concept(app: FastAPI, concept_id: str, body_text: str) -> None:
    """绕过 CONFIRMED 过滤直插 FTS 行：验证查询侧状态过滤的纵深防线。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO segment_search_index (body, entity_type, entity_id) "
                "VALUES (:body, 'CONCEPT', :concept_id)"
            ),
            {"body": tokenize(body_text), "concept_id": concept_id},
        )


async def seed_job(
    app: FastAPI,
    *,
    job_id: str,
    course_id: str,
    status: str,
    result_json: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
                "attempts, max_attempts, next_run_at, input_json, result_json, error_code, "
                "error_message, started_at, finished_at, created_at, updated_at, waiting_reason) "
                "VALUES (:id, NULL, 'CONCEPT_EXTRACTION', :status, 0, 0, 3, NULL, :input_json, "
                ":result_json, NULL, NULL, :now, :now, :now, :now, NULL)"
            ),
            {
                "id": job_id,
                "status": status,
                "input_json": json.dumps({"course_id": course_id}),
                "result_json": result_json,
                "now": NOW,
            },
        )


async def seed_anchor(
    app: FastAPI,
    *,
    anchor_id: str,
    course_id: str,
    source_type: str,
    source_id: str,
    record_id: str | None = None,
    transcript_segment_id: str | None = None,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO source_anchors (id, course_id, source_type, source_id, record_id, "
                "transcript_segment_id, document_segment_id) "
                "VALUES (:id, :course_id, :source_type, :source_id, :record_id, "
                ":transcript_segment_id, NULL)"
            ),
            {
                "id": anchor_id,
                "course_id": course_id,
                "source_type": source_type,
                "source_id": source_id,
                "record_id": record_id,
                "transcript_segment_id": transcript_segment_id,
            },
        )


async def link_concept_anchor(
    app: FastAPI,
    *,
    link_id: str,
    concept_id: str,
    anchor_id: str,
    relation_type: str = "PRIMARY",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO source_anchor_links (id, resource_type, resource_id, "
                "source_anchor_id, relation_type) "
                "VALUES (:id, 'CONCEPT', :concept_id, :anchor_id, :relation_type)"
            ),
            {
                "id": link_id,
                "concept_id": concept_id,
                "anchor_id": anchor_id,
                "relation_type": relation_type,
            },
        )


async def seed_relation(
    app: FastAPI,
    *,
    relation_id: str,
    course_id: str,
    source_concept_id: str,
    target_concept_id: str,
    relation_type: str = "RELATED_TO",
    status: str = "CONFIRMED",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO concept_relations (id, course_id, source_concept_id, "
                "target_concept_id, relation_type, confidence, evidence_count, status, "
                "created_at, updated_at) "
                "VALUES (:id, :course_id, :source_id, :target_id, :relation_type, 0.9, 1, "
                ":status, :now, :now)"
            ),
            {
                "id": relation_id,
                "course_id": course_id,
                "source_id": source_concept_id,
                "target_id": target_concept_id,
                "relation_type": relation_type,
                "status": status,
                "now": NOW,
            },
        )


async def seed_record_concept(
    app: FastAPI,
    *,
    rc_id: str,
    record_id: str,
    concept_id: str,
    kp_id: str | None = None,
    evidence_count: int = 1,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_concepts (id, record_id, concept_id, knowledge_point_id, "
                "relevance, evidence_count, first_start_ms, created_at, updated_at) "
                "VALUES (:id, :record_id, :concept_id, :kp_id, 0.8, :evidence_count, 1000, "
                ":now, :now)"
            ),
            {
                "id": rc_id,
                "record_id": record_id,
                "concept_id": concept_id,
                "kp_id": kp_id,
                "evidence_count": evidence_count,
                "now": NOW,
            },
        )


async def seed_chat_message(
    app: FastAPI, *, session_id: str, message_id: str, content: str
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO chat_sessions (id, course_id, mode, created_at, updated_at, "
                "deleted_at) VALUES (:id, NULL, 'ASK', :now, :now, NULL)"
            ),
            {"id": session_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO chat_messages (id, session_id, role, content, created_at) "
                "VALUES (:id, :session_id, 'ASSISTANT', :content, :now)"
            ),
            {"id": message_id, "session_id": session_id, "content": content, "now": NOW},
        )


async def soft_delete_record(app: FastAPI, record_id: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE records SET deleted_at = :now WHERE id = :id"),
            {"now": NOW, "id": record_id},
        )


async def run_search(
    app: FastAPI, course_id: str, query: str, limit: int = 8
) -> CourseBrainSearchOut:
    async with app.state.session_factory() as session:
        return await CourseBrainService.search(session, course_id, query, limit)


@pytest.mark.anyio
async def test_brain_snapshot_empty_then_ready_after_manual_create(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        empty = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert empty["status"] == "EMPTY"
        assert empty["concept_count"] == 0 and empty["candidate_count"] == 0

        created = await client.post(
            f"/api/courses/{COURSE_ID}/brain/concepts",
            json={"name": "MVCC", "description": "多版本并发控制"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "CONFIRMED"
        assert body["source"] == "USER_CONFIRMED"
        assert body["record_count"] == 0 and body["occurrence_count"] == 0

        ready = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert ready["status"] == "READY"
        assert ready["concept_count"] == 1 and ready["candidate_count"] == 0
        assert ready["stale"] is False


@pytest.mark.anyio
async def test_brain_snapshot_review_and_building(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_concept(
            app,
            concept_id="candidate-1",
            course_id=COURSE_ID,
            name="候选概念",
            status="CANDIDATE",
        )
        review = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert review["status"] == "REVIEW"
        assert review["candidate_count"] == 1 and review["concept_count"] == 0

        await seed_job(app, job_id="job-running", course_id=COURSE_ID, status="RUNNING")
        building = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert building["status"] == "BUILDING"
        assert building["active_job_id"] == "job-running"


@pytest.mark.anyio
async def test_brain_snapshot_stale_after_source_change(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        empty_fingerprint = {
            "transcript_segments": [0, None],
            "document_segments": [0, None],
            "knowledge_points": [0, None],
        }
        await seed_job(
            app,
            job_id="job-ok",
            course_id=COURSE_ID,
            status="SUCCEEDED",
            result_json=json.dumps({"fingerprint": empty_fingerprint}),
        )
        ready = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert ready["status"] == "READY"
        assert ready["stale"] is False
        assert ready["last_built_at"] is not None

        await seed_record(app, RECORD_ID, COURSE_ID)
        await seed_knowledge_point(app, kp_id=KP_ID, record_id=RECORD_ID)
        stale = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert stale["status"] == "STALE"
        assert stale["stale"] is True


@pytest.mark.anyio
async def test_brain_snapshot_failed_without_confirmed_concepts(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_job(app, job_id="job-fail", course_id=COURSE_ID, status="FAILED")
        failed = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert failed["status"] == "FAILED"

        await client.post(f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "MVCC"})
        ready = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert ready["status"] == "READY"


@pytest.mark.anyio
async def test_brain_concept_list_status_filter_and_pagination(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_concept(app, concept_id="concept-a", course_id=COURSE_ID, name="A")
        await seed_concept(app, concept_id="concept-b", course_id=COURSE_ID, name="B")
        await seed_concept(
            app, concept_id="concept-c", course_id=COURSE_ID, name="候选", status="CANDIDATE"
        )
        await seed_concept(
            app, concept_id="concept-d", course_id=COURSE_ID, name="退役", status="ARCHIVED"
        )
        default = (await client.get(f"/api/courses/{COURSE_ID}/brain/concepts")).json()
        assert [item["canonical_name"] for item in default] == ["A", "B"]

        candidates = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts?status=CANDIDATE")
        ).json()
        assert [item["canonical_name"] for item in candidates] == ["候选"]

        page = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts?limit=1&offset=1")
        ).json()
        assert [item["canonical_name"] for item in page] == ["B"]


@pytest.mark.anyio
async def test_brain_concept_detail_stats_and_cross_course_404(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_course(app, OTHER_COURSE_ID)
        await seed_concept(app, concept_id="concept-1", course_id=COURSE_ID, name="MVCC")
        await seed_record(app, RECORD_ID, COURSE_ID)
        await seed_record_concept(
            app,
            rc_id="rc-1",
            record_id=RECORD_ID,
            concept_id="concept-1",
            evidence_count=2,
        )
        detail = (await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1")).json()
        assert detail["record_count"] == 1 and detail["occurrence_count"] == 2

        cross = await client.get(f"/api/courses/{OTHER_COURSE_ID}/brain/concepts/concept-1")
        assert cross.status_code == 404
        assert cross.json()["code"] == "COURSE_BRAIN_CONCEPT_NOT_FOUND"

        missing = await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/missing")
        assert missing.status_code == 404

        await soft_delete_record(app, RECORD_ID)
        after_delete = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1")
        ).json()
        assert after_delete["record_count"] == 0 and after_delete["occurrence_count"] == 0


@pytest.mark.anyio
async def test_manual_create_normalized_duplicate_and_validation(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        created = await client.post(
            f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "MVCC"}
        )
        assert created.status_code == 201
        for name in ("mvcc", "  ＭＶＣＣ  ", "MVCC"):
            duplicate = await client.post(
                f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": name}
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "COURSE_BRAIN_CONCEPT_EXISTS"

        blank = await client.post(f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "   "})
        assert blank.status_code == 422
        bad_importance = await client.post(
            f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "X", "importance": 6}
        )
        assert bad_importance.status_code == 422


@pytest.mark.anyio
async def test_brain_endpoints_course_guards(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        paths = [
            f"/api/courses/{COURSE_ID}/brain",
            f"/api/courses/{COURSE_ID}/brain/concepts",
            f"/api/courses/{COURSE_ID}/brain/concepts/missing",
            f"/api/courses/{COURSE_ID}/brain/concepts/missing/sources",
        ]
        for path in paths:
            response = await client.get(path)
            assert response.status_code == 404
            assert response.json()["code"] == "COURSE_NOT_FOUND"
        response = await client.post(f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "X"})
        assert response.status_code == 404

        await seed_course(app, COURSE_ID, status="ARCHIVED")
        for path in paths:
            response = await client.get(path)
            assert response.status_code == 409
            assert response.json()["code"] == "COURSE_ARCHIVED"
        response = await client.post(f"/api/courses/{COURSE_ID}/brain/concepts", json={"name": "X"})
        assert response.status_code == 409


@pytest.mark.anyio
async def test_brain_search_matches_concept_and_expands_segments(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_record(app, RECORD_ID, COURSE_ID, title="数据库课程")
        await seed_transcript_segment(
            app,
            record_id=RECORD_ID,
            segment_id="seg-1",
            transcript_id="transcript-1",
            file_id="file-1",
            content="MVCC 通过 ReadView 实现事务可见性",
            start_ms=1000,
            end_ms=5000,
        )
        created = await client.post(
            f"/api/courses/{COURSE_ID}/brain/concepts",
            json={"name": "MVCC", "description": "多版本并发控制，通过快照读实现可见性"},
        )
        concept_id = created.json()["id"]
        await seed_record_concept(
            app, rc_id="rc-1", record_id=RECORD_ID, concept_id=concept_id, evidence_count=2
        )

        result = await run_search(app, COURSE_ID, "可见性")
        assert [concept.concept_id for concept in result.matched_concepts] == [concept_id]
        matcher = result.matched_concepts[0]
        assert matcher.record_count == 1 and matcher.occurrence_count == 2
        assert len(result.occurrences) == 1
        occurrence = result.occurrences[0]
        assert occurrence.quote == "MVCC 通过 ReadView 实现事务可见性"
        assert occurrence.record_id == RECORD_ID
        assert occurrence.record_title == "数据库课程"
        assert occurrence.start_ms == 1000 and occurrence.position == 0

        # 原查询与 canonical_name 并跑：以 "MVCC" 查询同样命中且去重后仅一条。
        mvcc_result = await run_search(app, COURSE_ID, "MVCC")
        assert len(mvcc_result.occurrences) == 1
        assert mvcc_result.occurrences[0].segment_id == "seg-1"

        # 同记录第二条命中：occurrences 逐条保留，去重计数由消费方按 record_id 处理。
        await seed_extra_transcript_segment(
            app,
            record_id=RECORD_ID,
            segment_id="seg-2",
            transcript_id="transcript-1",
            file_id="file-1",
            content="可见性判断依赖 ReadView",
            sequence_no=1,
        )
        expanded = await run_search(app, COURSE_ID, "可见性")
        assert len(expanded.occurrences) == 2
        assert {hit.record_id for hit in expanded.occurrences} == {RECORD_ID}


@pytest.mark.anyio
async def test_brain_search_ignores_candidates_and_other_courses(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_course(app, OTHER_COURSE_ID)
        await seed_concept(
            app,
            concept_id="candidate-1",
            course_id=COURSE_ID,
            name="候选并发",
            status="CANDIDATE",
        )
        await force_index_concept(app, "candidate-1", "候选并发 可见性")
        candidates = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts?status=CANDIDATE")
        ).json()
        assert [item["canonical_name"] for item in candidates] == ["候选并发"]
        result = await run_search(app, COURSE_ID, "可见性")
        assert result.matched_concepts == []
        assert result.occurrences == []

        await seed_concept(
            app,
            concept_id="concept-other",
            course_id=OTHER_COURSE_ID,
            name="其他课程概念",
            description="可见性",
        )
        cross = await run_search(app, COURSE_ID, "可见性")
        assert cross.matched_concepts == []


@pytest.mark.anyio
async def test_concept_sources_anchor_kp_chat_and_soft_delete(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_record(app, RECORD_ID, COURSE_ID, title="数据库课程")
        await seed_transcript_segment(
            app,
            record_id=RECORD_ID,
            segment_id="seg-1",
            transcript_id="transcript-1",
            file_id="file-1",
            content="MVCC 通过 ReadView 实现事务可见性",
            start_ms=1000,
            end_ms=5000,
        )
        await seed_concept(app, concept_id="concept-1", course_id=COURSE_ID, name="MVCC")
        await seed_anchor(
            app,
            anchor_id="anchor-audio",
            course_id=COURSE_ID,
            source_type="AUDIO_SEGMENT",
            source_id="seg-1",
            record_id=RECORD_ID,
            transcript_segment_id="seg-1",
        )
        await link_concept_anchor(
            app, link_id="link-1", concept_id="concept-1", anchor_id="anchor-audio"
        )
        await seed_knowledge_point(app, kp_id=KP_ID, record_id=RECORD_ID, name="MVCC 可见性")
        await seed_record_concept(
            app,
            rc_id="rc-1",
            record_id=RECORD_ID,
            concept_id="concept-1",
            kp_id=KP_ID,
        )
        await seed_chat_message(
            app, session_id="chat-session-1", message_id="chat-message-1", content="MVCC 要点"
        )
        await seed_anchor(
            app,
            anchor_id="anchor-chat",
            course_id=COURSE_ID,
            source_type="CHAT_MESSAGE",
            source_id="chat-message-1",
            record_id=RECORD_ID,
        )
        await link_concept_anchor(
            app, link_id="link-2", concept_id="concept-1", anchor_id="anchor-chat"
        )

        sources = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1/sources")
        ).json()
        anchors = {item["anchor_id"]: item for item in sources["anchors"]}
        assert set(anchors) == {"anchor-audio", "anchor-chat"}
        audio = anchors["anchor-audio"]
        assert audio["source_type"] == "AUDIO_SEGMENT"
        assert audio["quote"] == "MVCC 通过 ReadView 实现事务可见性"
        assert audio["start_ms"] == 1000 and audio["record_title"] == "数据库课程"
        chat = anchors["anchor-chat"]
        assert chat["chat_session_id"] == "chat-session-1" and chat["quote"] == "MVCC 要点"
        assert sources["knowledge_points"] == [
            {
                "record_id": RECORD_ID,
                "record_title": "数据库课程",
                "knowledge_point_id": KP_ID,
                "knowledge_point_name": "MVCC 可见性",
                "relevance": 0.8,
                "evidence_count": 1,
            }
        ]

        detail = (await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1")).json()
        assert detail["anchor_count"] == 2

        # 软删记录：来源回跳与 KP 桥全部失效，不泄漏。
        await soft_delete_record(app, RECORD_ID)
        after_delete = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1/sources")
        ).json()
        assert after_delete["anchors"] == []
        assert after_delete["knowledge_points"] == []
        after_detail = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1")
        ).json()
        assert after_detail["anchor_count"] == 0


@pytest.mark.anyio
async def test_concept_sources_only_active_knowledge_points(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_record(app, RECORD_ID, COURSE_ID, title="记录一")
        await seed_record(app, "record-2", COURSE_ID, title="记录二")
        await seed_concept(app, concept_id="concept-1", course_id=COURSE_ID, name="MVCC")
        await seed_knowledge_point(
            app, kp_id="kp-superseded", record_id=RECORD_ID, name="过期知识点", status="SUPERSEDED"
        )
        await seed_record_concept(
            app,
            rc_id="rc-superseded",
            record_id=RECORD_ID,
            concept_id="concept-1",
            kp_id="kp-superseded",
        )
        await seed_knowledge_point(app, kp_id="kp-active", record_id="record-2", name="有效知识点")
        await seed_record_concept(
            app, rc_id="rc-active", record_id="record-2", concept_id="concept-1", kp_id="kp-active"
        )

        sources = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/concept-1/sources")
        ).json()
        assert [item["knowledge_point_name"] for item in sources["knowledge_points"]] == [
            "有效知识点"
        ]


@pytest.mark.anyio
async def test_brain_search_related_concepts_confirmed_only(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, _client):
        await seed_course(app, COURSE_ID)
        await seed_course(app, OTHER_COURSE_ID)
        await seed_concept(
            app, concept_id="concept-1", course_id=COURSE_ID, name="MVCC", description="可见性"
        )
        await seed_concept(app, concept_id="concept-ok", course_id=COURSE_ID, name="快照读")
        await seed_concept(
            app,
            concept_id="concept-candidate",
            course_id=COURSE_ID,
            name="候选相关",
            status="CANDIDATE",
        )
        await seed_concept(
            app,
            concept_id="concept-archived",
            course_id=COURSE_ID,
            name="归档相关",
            status="ARCHIVED",
        )
        await seed_concept(
            app, concept_id="concept-other", course_id=OTHER_COURSE_ID, name="跨课程相关"
        )
        await seed_relation(
            app,
            relation_id="rel-ok",
            course_id=COURSE_ID,
            source_concept_id="concept-1",
            target_concept_id="concept-ok",
        )
        await seed_relation(
            app,
            relation_id="rel-candidate",
            course_id=COURSE_ID,
            source_concept_id="concept-1",
            target_concept_id="concept-candidate",
        )
        await seed_relation(
            app,
            relation_id="rel-archived",
            course_id=COURSE_ID,
            source_concept_id="concept-1",
            target_concept_id="concept-archived",
        )
        # 异常数据：关系行归属本课程但目标概念属于其他课程，同样不得泄漏。
        await seed_relation(
            app,
            relation_id="rel-other",
            course_id=COURSE_ID,
            source_concept_id="concept-1",
            target_concept_id="concept-other",
        )
        await seed_relation(
            app,
            relation_id="rel-candidate-status",
            course_id=COURSE_ID,
            source_concept_id="concept-1",
            target_concept_id="concept-ok",
            relation_type="APPLIES_TO",
            status="CANDIDATE",
        )

        result = await run_search(app, COURSE_ID, "可见性")
        assert [concept.concept_id for concept in result.related_concepts] == ["concept-ok"]


@pytest.mark.anyio
async def test_brain_search_respects_limit_and_truncates_quote(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_record(app, RECORD_ID, COURSE_ID)
        long_content = "可见性" * 300
        await seed_transcript_segment(
            app,
            record_id=RECORD_ID,
            segment_id="seg-1",
            transcript_id="transcript-1",
            file_id="file-1",
            content=long_content,
        )
        created = await client.post(
            f"/api/courses/{COURSE_ID}/brain/concepts",
            json={"name": "MVCC", "description": "可见性"},
        )
        assert created.status_code == 201
        for index in range(5):
            await seed_concept(
                app,
                concept_id=f"concept-extra-{index}",
                course_id=COURSE_ID,
                name=f"补充概念{index}",
                description="可见性",
            )

        capped = await run_search(app, COURSE_ID, "可见性", limit=8)
        assert len(capped.matched_concepts) == 4
        result = await run_search(app, COURSE_ID, "可见性", limit=1)
        assert len(result.occurrences) == 1
        assert len(result.occurrences[0].quote) == 500
        assert long_content.startswith(result.occurrences[0].quote)


# ---------------------------------------------------------------------------
# CB-04 多来源收集与构建 Worker（job_type=CONCEPT_EXTRACTION）
# ---------------------------------------------------------------------------

BRAIN_OUTPUT: dict[str, object] = {
    "concepts": [
        {
            "name": "MVCC",
            "description": "多版本并发控制",
            "concept_type": "TERM",
            "importance": 5,
            "evidence": [
                {"quote": "MVCC 通过 ReadView 实现事务可见性", "source_hint": "转写"},
            ],
        },
        {
            "name": "ReadView",
            "description": "一致性视图",
            "concept_type": "TERM",
            "importance": 4,
            "evidence": [
                {"quote": "可见性判断依赖 ReadView", "source_hint": "文档"},
            ],
        },
    ],
    "relations": [
        {
            "source": "MVCC",
            "target": "ReadView",
            "relation_type": "PART_OF",
            "confidence": 0.8,
        }
    ],
}


class FakeCourseBrainModel:
    def __init__(self, output: object | None = None) -> None:
        self.output = output if output is not None else BRAIN_OUTPUT
        self.prompts: list[str] = []
        self.error: Exception | None = None
        self.release = asyncio.Event()
        self.release.set()

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        assert base_url == "https://example.com/v1"
        assert api_key == "sk-test"
        assert model == "qwen-plus"
        self.prompts.append(prompt)
        await self.release.wait()
        if self.error is not None:
            raise self.error
        return StructuredModelResult(output=self.output, token_usage={"total_tokens": 21})


@asynccontextmanager
async def running_brain_worker_app(
    data_dir: Path, model: FakeCourseBrainModel
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN, course_brain_model=model)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def configure_llm(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert response.status_code == 200


async def grant_llm_consent(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/settings/external-processing-consents/llm")
    assert response.status_code == 200


async def seed_document_segment(
    app: FastAPI,
    *,
    course_id: str,
    record_id: str,
    segment_id: str,
    file_id: str,
    content: str,
    page_no: int = 1,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
                "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'DOCUMENT', 'UPLOADED', 'p.pdf', 'p.pdf', "
                "'application/pdf', 1, 0, 1, 'h', :now, :now, NULL)"
            ),
            {"id": file_id, "record_id": record_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
                "sequence_no, page_no, content, content_hash) "
                "VALUES (:id, :course_id, :record_id, :file_id, 0, :page_no, :content, "
                ":content_hash)"
            ),
            {
                "id": segment_id,
                "course_id": course_id,
                "record_id": record_id,
                "file_id": file_id,
                "page_no": page_no,
                "content": content,
                "content_hash": content_hash(content),
            },
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, [segment_id]
        )


async def link_anchor(
    app: FastAPI,
    *,
    link_id: str,
    resource_type: str,
    resource_id: str,
    anchor_id: str,
    relation_type: str = "PRIMARY",
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO source_anchor_links (id, resource_type, resource_id, "
                "source_anchor_id, relation_type) "
                "VALUES (:id, :resource_type, :resource_id, :anchor_id, :relation_type)"
            ),
            {
                "id": link_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "anchor_id": anchor_id,
                "relation_type": relation_type,
            },
        )


async def wait_for_brain_status(
    client: httpx.AsyncClient, course_id: str, expected: str, attempts: int = 300
) -> dict[str, object]:
    for _ in range(attempts):
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/courses/{course_id}/brain")).json(),
        )
        if payload["status"] == expected:
            return payload
        await asyncio.sleep(0.02)
    pytest.fail(f"课程大脑未进入 {expected}")


async def wait_for_job_status(
    app: FastAPI, job_id: str, expected: str, attempts: int = 300
) -> dict[str, object]:
    for _ in range(attempts):
        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, error_code, result_json FROM processing_jobs "
                        "WHERE id = :job_id"
                    ),
                    {"job_id": job_id},
                )
            ).one()
        status = cast(str, row[0])
        if status == expected:
            return {"status": status, "error_code": row[1], "result_json": row[2]}
        await asyncio.sleep(0.02)
    pytest.fail(f"构建任务未进入 {expected}")


async def count_rows(app: FastAPI, table: str) -> int:
    async with app.state.session_factory() as session:
        return int(await session.scalar(text(f"SELECT count(*) FROM {table}")) or 0)


async def seed_full_sources(app: FastAPI) -> None:
    """一条记录聚合转写分片 + 文档分片 + ACTIVE KP + 该 KP 的对话锚点。"""
    await seed_record(app, RECORD_ID, COURSE_ID, title="数据库课程")
    await seed_transcript_segment(
        app,
        record_id=RECORD_ID,
        segment_id="seg-1",
        transcript_id="transcript-1",
        file_id="file-1",
        content="MVCC 通过 ReadView 实现事务可见性",
        start_ms=1000,
        end_ms=5000,
    )
    await seed_document_segment(
        app,
        course_id=COURSE_ID,
        record_id=RECORD_ID,
        segment_id="doc-seg-1",
        file_id="doc-file-1",
        content="本页说明可见性判断依赖 ReadView 的快照读机制",
        page_no=2,
    )
    await seed_knowledge_point(app, kp_id=KP_ID, record_id=RECORD_ID, name="MVCC")
    await seed_chat_message(
        app, session_id="chat-session-1", message_id="chat-message-1", content="MVCC 要点"
    )
    await seed_anchor(
        app,
        anchor_id="anchor-chat",
        course_id=COURSE_ID,
        source_type="CHAT_MESSAGE",
        source_id="chat-message-1",
        record_id=RECORD_ID,
    )
    await link_anchor(
        app,
        link_id="kp-chat-link",
        resource_type="KNOWLEDGE_POINT",
        resource_id=KP_ID,
        anchor_id="anchor-chat",
    )


@pytest.mark.anyio
async def test_build_collects_multi_source_and_publishes_candidates(tmp_path: Path) -> None:
    model = FakeCourseBrainModel()
    async with running_brain_worker_app(tmp_path / "KnowRealm", model) as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_full_sources(app)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]
        snapshot = await wait_for_brain_status(client, COURSE_ID, "REVIEW")
        assert snapshot["candidate_count"] == 2 and snapshot["concept_count"] == 0

        candidates = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts?status=CANDIDATE")
        ).json()
        by_name = {item["canonical_name"]: item["id"] for item in candidates}
        assert set(by_name) == {"MVCC", "ReadView"}

        mvcc_sources = (
            await client.get(f"/api/courses/{COURSE_ID}/brain/concepts/{by_name['MVCC']}/sources")
        ).json()
        assert {anchor["source_type"] for anchor in mvcc_sources["anchors"]} == {
            "AUDIO_SEGMENT",
            "CHAT_MESSAGE",
        }
        assert mvcc_sources["knowledge_points"] == [
            {
                "record_id": RECORD_ID,
                "record_title": "数据库课程",
                "knowledge_point_id": KP_ID,
                "knowledge_point_name": "MVCC",
                "relevance": 1.0,
                "evidence_count": 1,
            }
        ]
        readview_sources = (
            await client.get(
                f"/api/courses/{COURSE_ID}/brain/concepts/{by_name['ReadView']}/sources"
            )
        ).json()
        assert [anchor["source_type"] for anchor in readview_sources["anchors"]] == [
            "DOCUMENT_SEGMENT"
        ]
        assert readview_sources["anchors"][0]["page_no"] == 2
        assert readview_sources["knowledge_points"] == []

        result = json.loads(
            cast(str, (await wait_for_job_status(app, job_id, "SUCCEEDED"))["result_json"])
        )
        assert result["concept_count"] == 2 and result["candidate_count"] == 2
        assert set(result["fingerprint"]) == {
            "transcript_segments",
            "document_segments",
            "knowledge_points",
        }

        async with app.state.session_factory() as session:
            relations = (
                await session.execute(
                    text(
                        "SELECT source_concept_id, target_concept_id, relation_type, status "
                        "FROM concept_relations"
                    )
                )
            ).all()
            log_row = (
                await session.execute(
                    text(
                        "SELECT graph_name, graph_node, prompt_version "
                        "FROM llm_call_logs WHERE graph_name = 'course-brain'"
                    )
                )
            ).one()
        assert relations == [(by_name["MVCC"], by_name["ReadView"], "PART_OF", "CANDIDATE")]
        assert log_row == ("course-brain", "extract", "course_brain_v1")
        assert await count_rows(app, "learning_events") == 0
        assert len(model.prompts) == 1
        assert "学习场景：INTEREST" in model.prompts[0]
        assert "MVCC 通过 ReadView 实现事务可见性" in model.prompts[0]
        assert "已确认知识点：\n- MVCC" in model.prompts[0]


@pytest.mark.anyio
async def test_rebuild_is_idempotent_and_reuses_confirmed_concept(tmp_path: Path) -> None:
    model = FakeCourseBrainModel()
    async with running_brain_worker_app(tmp_path / "KnowRealm", model) as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_full_sources(app)
        await seed_concept(app, concept_id="concept-mvcc", course_id=COURSE_ID, name="MVCC")
        await configure_llm(client)
        await grant_llm_consent(client)

        first = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert first.status_code == 202
        await wait_for_brain_status(client, COURSE_ID, "REVIEW")

        concepts_after_first = await count_rows(app, "concepts")
        occurrences_after_first = await count_rows(app, "record_concepts")
        anchors_after_first = await count_rows(app, "source_anchors")
        relations_after_first = await count_rows(app, "concept_relations")
        assert concepts_after_first == 2  # 1 复用 CONFIRMED + 1 新候选
        assert occurrences_after_first == 2
        assert anchors_after_first == 3  # 对话锚点 + 转写锚点 + 文档锚点
        assert relations_after_first == 1

        second = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert second.status_code == 202
        await wait_for_job_status(app, second.json()["job_id"], "SUCCEEDED")

        assert await count_rows(app, "concepts") == concepts_after_first
        assert await count_rows(app, "record_concepts") == occurrences_after_first
        assert await count_rows(app, "source_anchors") == anchors_after_first
        assert await count_rows(app, "concept_relations") == relations_after_first
        async with app.state.session_factory() as session:
            confirmed = await session.scalar(
                text("SELECT count(*) FROM concepts WHERE status = 'CONFIRMED'")
            )
            mvcc = await session.scalar(
                text("SELECT status FROM concepts WHERE id = 'concept-mvcc'")
            )
        assert confirmed == 1, "重复构建不得新增或覆盖正式节点"
        assert mvcc == "CONFIRMED"


@pytest.mark.anyio
async def test_build_failure_keeps_previous_graph(tmp_path: Path) -> None:
    model = FakeCourseBrainModel()
    async with running_brain_worker_app(tmp_path / "KnowRealm", model) as (app, client):
        await seed_course(app, COURSE_ID)
        await seed_full_sources(app)
        await seed_concept(app, concept_id="concept-mvcc", course_id=COURSE_ID, name="MVCC")
        await seed_concept(app, concept_id="concept-readview", course_id=COURSE_ID, name="ReadView")
        await seed_record_concept(
            app, rc_id="rc-kept", record_id=RECORD_ID, concept_id="concept-mvcc"
        )
        await seed_relation(
            app,
            relation_id="rel-kept",
            course_id=COURSE_ID,
            source_concept_id="concept-mvcc",
            target_concept_id="concept-readview",
        )
        await configure_llm(client)
        await grant_llm_consent(client)
        model.error = StructuredGenerationError("PROVIDER_REQUEST_FAILED")

        accepted = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert accepted.status_code == 202
        job = await wait_for_job_status(app, accepted.json()["job_id"], "FAILED")

        assert job["error_code"] == "PROVIDER_REQUEST_FAILED"
        assert await count_rows(app, "concepts") == 2
        assert await count_rows(app, "record_concepts") == 1
        assert await count_rows(app, "concept_relations") == 1
        snapshot = (await client.get(f"/api/courses/{COURSE_ID}/brain")).json()
        assert snapshot["status"] == "READY" and snapshot["stale"] is False


@pytest.mark.anyio
async def test_build_trigger_guards(tmp_path: Path) -> None:
    async with running_brain_app(tmp_path / "KnowRealm") as (app, client):
        await seed_course(app, COURSE_ID)
        unconfigured = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert unconfigured.status_code == 409
        assert unconfigured.json()["code"] == "LLM_PROVIDER_UNCONFIGURED"

        await configure_llm(client)
        no_consent = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert no_consent.status_code == 409
        assert no_consent.json()["code"] == "AI_CONSENT_REQUIRED"

        await grant_llm_consent(client)
        await seed_job(app, job_id="job-active", course_id=COURSE_ID, status="RUNNING")
        in_progress = await client.post(f"/api/courses/{COURSE_ID}/brain/builds")
        assert in_progress.status_code == 409
        assert in_progress.json()["code"] == "COURSE_BRAIN_BUILD_IN_PROGRESS"

        await seed_course(app, OTHER_COURSE_ID, status="ARCHIVED")
        archived = await client.post(f"/api/courses/{OTHER_COURSE_ID}/brain/builds")
        assert archived.status_code == 409
        assert archived.json()["code"] == "COURSE_ARCHIVED"

        missing = await client.post("/api/courses/missing-course/brain/builds")
        assert missing.status_code == 404
        assert missing.json()["code"] == "COURSE_NOT_FOUND"


@pytest.mark.anyio
async def test_build_preflight_waits_for_provider_and_consent(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    assert await preflight(data_dir) is None

    await asyncio.to_thread(
        save_llm_provider,
        data_dir,
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="qwen-plus",
        clear_api_key=False,
    )
    assert await preflight(data_dir) is None, "有 key 但无同意时仍应等待"

    await asyncio.to_thread(grant_llm_consent_file, data_dir)
    provider = await preflight(data_dir)
    assert provider is not None and provider.model == "qwen-plus"


@pytest.mark.anyio
async def test_build_worker_recovers_interrupted_running_job(tmp_path: Path) -> None:
    model = FakeCourseBrainModel()
    async with running_brain_worker_app(tmp_path / "KnowRealm", model) as (app, _client):
        await seed_course(app, COURSE_ID)
        await seed_job(app, job_id="job-running", course_id=COURSE_ID, status="RUNNING")

        spec = course_brain_spec(
            app.state.session_factory,
            app.state.data_dir,
            model,
            app.state.record_notifier,
        )
        await spec.recover_interrupted()

        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT status, error_code FROM processing_jobs WHERE id = 'job-running'")
                )
            ).one()
        assert row == ("FAILED", "WORKER_INTERRUPTED")
