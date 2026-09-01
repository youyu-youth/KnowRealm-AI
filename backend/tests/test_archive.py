"""全量导出/导入与滚动备份：zip 结构、导入校验矩阵、user_version 双向、备份清理。"""

import datetime as dt
import json
import re
import zipfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from sqlite3 import connect

import httpx
import pytest
from fastapi import FastAPI

from app.core.data_dir import ensure_data_dir
from app.core.version import APP_VERSION
from app.db.migrations import MIGRATIONS_DIR, run_migrations, supported_user_version
from app.main import create_app
from app.modules.data.archive import (
    KEEP_BACKUPS,
    MANIFEST_NAME,
    ImportArchiveError,
    create_rolling_backup,
    export_archive,
    restore_archive,
)

TOKEN = "test-launch-token"
EXPORT_NAME = re.compile(r"knowrealm-export-\d{8}-\d{6}\.zip")
COURSE_SQL = """
INSERT INTO courses (
    id, name, learning_context, education_stage, depth,
    course_type, description, hot_words, status,
    created_at, updated_at, deleted_at
) VALUES (
    '11111111-1111-4111-8111-111111111111', '导出课程', 'INTEREST', NULL, 'BEGINNER',
    NULL, NULL, NULL, 'ACTIVE', '2026-08-30T08:00:00.000000Z', '2026-08-30T08:00:00.000000Z', NULL
)
"""


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def seed_data_dir(data_dir: Path) -> Path:
    """就绪一个带课程、档案文件与配置的数据目录。"""
    ensure_data_dir(data_dir)
    await run_migrations(data_dir / "knowrealm.db")
    with connect(data_dir / "knowrealm.db") as connection:
        connection.execute(COURSE_SQL)
    (data_dir / "files" / "avatar.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    record_dir = data_dir / "files" / "22222222-2222-4222-8222-222222222222"
    record_dir.mkdir(parents=True)
    (record_dir / "doc.txt").write_bytes(b"doc-body")
    (data_dir / "config" / "settings.json").write_text("{}", encoding="utf-8")
    (data_dir / "config" / "providers.json").write_text('{"llm": {}}', encoding="utf-8")
    # 不入包的内容：临时文件与历史导出物
    (data_dir / "cache" / "imports").mkdir(parents=True, exist_ok=True)
    (data_dir / "cache" / "imports" / "x.tmp").write_bytes(b"tmp")
    (data_dir / "exports" / "old.zip").write_bytes(b"old")
    (data_dir / "backups" / "knowrealm-20200101.db").write_bytes(b"old-backup")
    (data_dir / "langgraph.db").write_bytes(b"checkpoints")
    return data_dir


def build_partial_db(db_path: Path, upto: int) -> None:
    """只应用前 upto 个迁移，得到旧版本库（导入自动升级矩阵用）。"""
    with connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        scripts = sorted(MIGRATIONS_DIR.glob("*.sql"))[:upto]
        for version, path in enumerate(scripts, start=1):
            sql = path.read_text(encoding="utf-8")
            connection.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={version};\nCOMMIT;")


def craft_archive(zip_path: Path, db_path: Path, *, user_version: int | None = None) -> None:
    with connect(db_path) as connection:
        actual = connection.execute("PRAGMA user_version").fetchone()[0]
    manifest = {
        "app_version": APP_VERSION,
        "db_user_version": actual if user_version is None else user_version,
        "created_at": "2026-08-30T00:00:00+08:00",
        "include_secrets": False,
        "files": ["knowrealm.db"],
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(db_path, "knowrealm.db")
        archive.writestr("manifest.json", json.dumps(manifest))


def code_of(error: Exception) -> str:
    return str(error).split("：", 1)[0]


@pytest.mark.anyio
async def test_export_builds_zip_with_manifest_and_excludes_secrets(tmp_path: Path) -> None:
    data_dir = await seed_data_dir(tmp_path / "KnowRealm")

    file_name = await export_archive(data_dir, include_secrets=False)

    assert EXPORT_NAME.fullmatch(file_name)
    assert (data_dir / "exports" / file_name).is_file()
    with zipfile.ZipFile(data_dir / "exports" / file_name) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))

    assert set(names) == {
        "manifest.json",
        "knowrealm.db",
        "files/avatar.png",
        "files/22222222-2222-4222-8222-222222222222/doc.txt",
        "config/settings.json",
    }
    assert manifest["app_version"] == APP_VERSION
    assert manifest["db_user_version"] == supported_user_version()
    assert manifest["include_secrets"] is False
    assert manifest["created_at"]
    assert manifest["files"] == [
        "knowrealm.db",
        "files/22222222-2222-4222-8222-222222222222/doc.txt",
        "files/avatar.png",
        "config/settings.json",
    ]
    extracted = tmp_path / "exported.db"
    with zipfile.ZipFile(data_dir / "exports" / file_name) as archive:
        extracted.write_bytes(archive.read("knowrealm.db"))
    with connect(extracted) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == supported_user_version()
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] == 1


@pytest.mark.anyio
async def test_export_includes_providers_when_secrets_requested(tmp_path: Path) -> None:
    data_dir = await seed_data_dir(tmp_path / "KnowRealm")

    file_name = await export_archive(data_dir, include_secrets=True)

    with zipfile.ZipFile(data_dir / "exports" / file_name) as archive:
        assert "config/providers.json" in archive.namelist()
        assert json.loads(archive.read("manifest.json"))["include_secrets"] is True


@pytest.mark.anyio
async def test_restore_round_trips_into_fresh_directory(tmp_path: Path) -> None:
    source = await seed_data_dir(tmp_path / "A")
    file_name = await export_archive(source, include_secrets=True)
    target = ensure_data_dir(tmp_path / "B")

    await restore_archive(target, source / "exports" / file_name)

    with connect(target / "knowrealm.db") as connection:
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == supported_user_version()
    assert (target / "files" / "avatar.png").read_bytes() == b"\x89PNG\r\n\x1a\nfake"
    assert (
        target / "files" / "22222222-2222-4222-8222-222222222222" / "doc.txt"
    ).read_bytes() == b"doc-body"
    assert (target / "config" / "providers.json").read_text(encoding="utf-8") == '{"llm": {}}'
    assert not (target / "cache" / "import-archive").exists()


@pytest.mark.anyio
async def test_restore_upgrades_older_database_via_existing_migrations(tmp_path: Path) -> None:
    old_db = tmp_path / "old.db"
    build_partial_db(old_db, upto=max(supported_user_version() - 1, 1))
    archive_path = tmp_path / "old-export.zip"
    craft_archive(archive_path, old_db)
    target = ensure_data_dir(tmp_path / "B")

    await restore_archive(target, archive_path)

    with connect(target / "knowrealm.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] < supported_user_version()
    await run_migrations(target / "knowrealm.db")
    with connect(target / "knowrealm.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == supported_user_version()


@pytest.mark.anyio
async def test_restore_rejects_invalid_archives_without_residue(tmp_path: Path) -> None:
    target = ensure_data_dir(tmp_path / "B")

    not_a_zip = tmp_path / "not-a-zip.zip"
    not_a_zip.write_text("plain text", encoding="utf-8")
    with pytest.raises(ImportArchiveError) as missing:
        await restore_archive(target, tmp_path / "gone.zip")
    with pytest.raises(ImportArchiveError) as invalid:
        await restore_archive(target, not_a_zip)
    assert code_of(missing.value) == "IMPORT_ARCHIVE_MISSING"
    assert code_of(invalid.value) == "IMPORT_ARCHIVE_INVALID"

    # 缺 manifest
    no_manifest = tmp_path / "no-manifest.zip"
    with zipfile.ZipFile(no_manifest, "w") as archive:
        archive.writestr("knowrealm.db", b"db")
    # 结构不符：包内多出清单未声明的文件
    mismatch = tmp_path / "mismatch.zip"
    with zipfile.ZipFile(mismatch, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "app_version": APP_VERSION,
                    "db_user_version": 1,
                    "created_at": "2026-08-30T00:00:00+08:00",
                    "include_secrets": False,
                    "files": ["knowrealm.db"],
                }
            ),
        )
        archive.writestr("knowrealm.db", b"db")
        archive.writestr("files/extra.txt", b"stowaway")
    # 清单声明了包内不存在的文件
    ghost = tmp_path / "ghost.zip"
    with zipfile.ZipFile(ghost, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "app_version": APP_VERSION,
                    "db_user_version": 1,
                    "created_at": "2026-08-30T00:00:00+08:00",
                    "include_secrets": False,
                    "files": ["knowrealm.db", "files/ghost.txt"],
                }
            ),
        )
        archive.writestr("knowrealm.db", b"db")
    for path, expected in (
        (no_manifest, "IMPORT_ARCHIVE_INVALID"),
        (mismatch, "IMPORT_ARCHIVE_INVALID"),
        (ghost, "IMPORT_ARCHIVE_INVALID"),
    ):
        with pytest.raises(ImportArchiveError) as rejected:
            await restore_archive(target, path)
        assert code_of(rejected.value) == expected

    assert not (target / "knowrealm.db").exists()
    assert list((target / "files").iterdir()) == []
    assert not (target / "cache" / "import-archive").exists()


@pytest.mark.anyio
async def test_restore_rejects_archive_from_newer_app_version(tmp_path: Path) -> None:
    source = await seed_data_dir(tmp_path / "A")
    file_name = await export_archive(source, include_secrets=False)
    newer = tmp_path / "newer-export.zip"
    with (
        zipfile.ZipFile(source / "exports" / file_name) as original,
        zipfile.ZipFile(newer, "w") as rewritten,
    ):
        manifest = json.loads(original.read("manifest.json"))
        manifest["db_user_version"] = supported_user_version() + 5
        for name in original.namelist():
            rewritten.writestr(
                name,
                json.dumps(manifest) if name == "manifest.json" else original.read(name),
            )
    target = ensure_data_dir(tmp_path / "B")

    with pytest.raises(ImportArchiveError) as rejected:
        await restore_archive(target, newer)

    assert code_of(rejected.value) == "IMPORT_ARCHIVE_VERSION_TOO_NEW"
    assert "高于当前应用" in str(rejected.value)
    assert not (target / "knowrealm.db").exists()
    assert not (target / "cache" / "import-archive").exists()


@pytest.mark.anyio
async def test_restore_rejects_non_empty_target_library(tmp_path: Path) -> None:
    source = await seed_data_dir(tmp_path / "A")
    file_name = await export_archive(source, include_secrets=False)
    target = await seed_data_dir(tmp_path / "B")

    with pytest.raises(ImportArchiveError) as rejected:
        await restore_archive(target, source / "exports" / file_name)

    assert code_of(rejected.value) == "IMPORT_ARCHIVE_TARGET_NOT_EMPTY"
    with connect(target / "knowrealm.db") as connection:
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] == 1
    assert (target / "files" / "avatar.png").read_bytes() == b"\x89PNG\r\n\x1a\nfake"


@pytest.mark.anyio
async def test_rolling_backup_snapshots_once_per_day_and_prunes_to_limit(tmp_path: Path) -> None:
    data_dir = await seed_data_dir(tmp_path / "KnowRealm")
    backups = data_dir / "backups"
    for day in range(1, 10):
        (backups / f"knowrealm-2026010{day}.db").write_bytes(b"stale")

    await create_rolling_backup(data_dir / "knowrealm.db", backups)
    await create_rolling_backup(data_dir / "knowrealm.db", backups)

    remaining = sorted(path.name for path in backups.glob("knowrealm-*.db"))
    assert len(remaining) == KEEP_BACKUPS
    assert f"knowrealm-{dt.datetime.now():%Y%m%d}.db" in remaining
    assert "knowrealm-20260109.db" in remaining  # 较新的旧快照保留
    assert "knowrealm-20260101.db" not in remaining  # 最旧的被清理


@asynccontextmanager
async def running_app(
    data_dir: Path, import_archive: Path | None = None
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient], None]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN, import_archive=import_archive)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


@pytest.mark.anyio
async def test_library_state_endpoint_reflects_emptiness(tmp_path: Path) -> None:
    async with running_app(tmp_path / "Empty") as (_app, client):
        empty = await client.get("/api/settings/data-directory/library-state")
        assert empty.status_code == 200
        assert empty.json() == {"empty_library": True}

    seeded = await seed_data_dir(tmp_path / "Seeded")
    async with running_app(seeded) as (_app, client):
        non_empty = await client.get("/api/settings/data-directory/library-state")
        assert non_empty.json() == {"empty_library": False}


@pytest.mark.anyio
async def test_export_endpoint_writes_zip_into_exports(tmp_path: Path) -> None:
    data_dir = await seed_data_dir(tmp_path / "KnowRealm")
    async with running_app(data_dir) as (_app, client):
        created = await client.post(
            "/api/settings/data-directory/export", json={"include_secrets": False}
        )

    assert created.status_code == 200
    file_name = created.json()["file_name"]
    assert EXPORT_NAME.fullmatch(file_name)
    assert (data_dir / "exports" / file_name).is_file()


@pytest.mark.anyio
async def test_lifespan_imports_archive_before_opening_database(tmp_path: Path) -> None:
    source = await seed_data_dir(tmp_path / "A")
    file_name = await export_archive(source, include_secrets=False)
    target = tmp_path / "B"
    async with running_app(target, import_archive=source / "exports" / file_name) as (
        _app,
        client,
    ):
        courses = await client.get("/api/courses")

    assert courses.status_code == 200
    assert [course["name"] for course in courses.json()] == ["导出课程"]


@pytest.mark.anyio
async def test_lifespan_rejects_invalid_import_archive_without_residue(tmp_path: Path) -> None:
    bad_archive = tmp_path / "bad.zip"
    bad_archive.write_text("not a zip", encoding="utf-8")
    target = tmp_path / "B"

    with pytest.raises(ImportArchiveError) as rejected:
        async with running_app(target, import_archive=bad_archive):
            pass

    assert code_of(rejected.value) == "IMPORT_ARCHIVE_INVALID"
    assert not (target / "knowrealm.db").exists()


@pytest.mark.anyio
async def test_lifespan_creates_daily_rolling_backup(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir):
        pass
    daily = data_dir / "backups" / f"knowrealm-{dt.datetime.now():%Y%m%d}.db"
    assert daily.is_file()
    with connect(daily) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == supported_user_version()

    async with running_app(data_dir):
        pass
    assert len(list((data_dir / "backups").glob("knowrealm-*.db"))) == 1


@pytest.mark.anyio
async def test_export_manifest_stays_consistent_when_file_vanishes_mid_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """导出期间不停写：并发删除的文件被跳过时，清单必须同步剔除，产物仍可导入。"""
    from app.modules.data import archive as archive_service

    data_dir = await seed_data_dir(tmp_path / "KnowRealm")
    real_collect = archive_service._collect_entries  # pyright: ignore[reportPrivateUsage]

    def collect_with_vanished(root: Path, include_secrets: bool) -> list[str]:
        return [*real_collect(root, include_secrets), "files/already-gone.txt"]

    monkeypatch.setattr(  # pyright: ignore[reportPrivateUsage]
        archive_service, "_collect_entries", collect_with_vanished
    )

    file_name = await export_archive(data_dir, include_secrets=False)

    with zipfile.ZipFile(data_dir / "exports" / file_name) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert "files/already-gone.txt" not in names
    assert set(manifest["files"]) == set(names) - {MANIFEST_NAME}

    target = ensure_data_dir(tmp_path / "B")
    await restore_archive(target, data_dir / "exports" / file_name)
    assert (target / "knowrealm.db").exists()


@pytest.mark.anyio
async def test_export_excludes_atomic_write_temp_files(tmp_path: Path) -> None:
    """local_config 原子写的 config/*.tmp（含明文密钥的 providers.tmp）永不入包。"""
    data_dir = await seed_data_dir(tmp_path / "KnowRealm")
    (data_dir / "config" / "providers.tmp").write_text('{"llm": "secret"}', encoding="utf-8")

    file_name = await export_archive(data_dir, include_secrets=False)

    with zipfile.ZipFile(data_dir / "exports" / file_name) as archive:
        assert "config/providers.tmp" not in archive.namelist()
        assert "config/providers.tmp" not in json.loads(archive.read("manifest.json"))["files"]
