"""全量导出/导入与滚动备份。

导出包结构：manifest.json + knowrealm.db（VACUUM INTO 快照）+ files/** + config/**；
默认排除 config/providers.json，勾选含密钥时随包并明示明文风险（由前端提示）。
导入在 lifespan 中 ensure_data_dir 之后、目录锁与开库之前执行：全部拒绝路径不落盘。
"""

import asyncio
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from re import fullmatch
from sqlite3 import OperationalError
from typing import NoReturn, cast
from uuid import uuid4

import aiosqlite
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.version import APP_VERSION
from app.db.migrations import supported_user_version

MANIFEST_NAME = "manifest.json"
DB_ENTRY = "knowrealm.db"
PROVIDERS_ENTRY = "config/providers.json"
EXPORT_PREFIX = "knowrealm-export-"
BACKUP_PATTERN = r"knowrealm-\d{8}\.db"
KEEP_BACKUPS = 7

# 空库判定：无课程 + 无记录 + 无档案（软删数据仍在，视为非空以保证误导入可回退）。
EMPTY_LIBRARY_SQL = (
    "SELECT 1 FROM courses WHERE deleted_at IS NULL LIMIT 1",
    "SELECT 1 FROM records WHERE deleted_at IS NULL LIMIT 1",
    "SELECT 1 FROM profile LIMIT 1",
)


class ImportArchiveError(RuntimeError):
    """导出包校验失败；message 形如 `IMPORT_ARCHIVE_*：中文说明`。"""


def _reject(code: str, detail: str) -> NoReturn:
    raise ImportArchiveError(f"{code}：{detail}")


async def vacuum_into(db_path: Path, target: Path) -> None:
    """WAL 安全的库快照：另开连接 VACUUM INTO，不阻塞其余写入连接。"""
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("VACUUM INTO ?", (str(target),))


async def read_user_version(db_path: Path) -> int:
    async with aiosqlite.connect(db_path) as connection:
        row = await (await connection.execute("PRAGMA user_version")).fetchone()
    if row is None:
        raise RuntimeError("无法读取数据库版本")
    return cast(int, row[0])


async def ensure_pre_upgrade_snapshot(db_path: Path, backups_dir: Path) -> None:
    """升级前快照（library-rag-v1 迁移纪律）：旧库版本低于 sidecar 支持版本时，
    在应用新 Schema 前用 VACUUM INTO 落一份独立快照（每个目标版本一份，已存在
    不覆盖——保留首次升级前状态）。失败抛错由 lifespan 终止启动：不得无保护升级。
    命名不匹配滚动备份清理模式，不会被 7 份滚动上限清掉。"""
    if not db_path.exists():
        return
    current = await read_user_version(db_path)
    target = supported_user_version()
    if current >= target:
        return
    snapshot = backups_dir / f"knowrealm-premigrate-{target:04d}.db"
    if snapshot.exists():
        return
    backups_dir.mkdir(exist_ok=True)
    await vacuum_into(db_path, snapshot)
    logger.info("pre_upgrade_snapshot_created", current=current, target=target)


def _collect_entries(data_dir: Path, include_secrets: bool) -> list[str]:
    entries: list[str] = []
    for root_name in ("files", "config"):
        root = data_dir / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                # *.tmp 是 local_config 原子写的中间文件（含明文密钥的 providers.tmp），
                # 瞬态存在，永不入包。
                if path.suffix == ".tmp":
                    continue
                relative = path.relative_to(data_dir).as_posix()
                if relative == PROVIDERS_ENTRY and not include_secrets:
                    continue
                entries.append(relative)
    return entries


def _build_zip(
    zip_path: Path,
    snapshot: Path,
    data_dir: Path,
    entries: list[str],
    manifest: dict[str, object],
) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        written = [DB_ENTRY]
        archive.write(snapshot, DB_ENTRY)
        for relative in entries:
            source = data_dir / Path(*PurePosixPath(relative).parts)
            try:
                archive.write(source, relative)
            except FileNotFoundError:
                # 导出期间不停写：并发删除的文件跳过，不中断整个导出；
                # 清单必须同步剔除，否则产出导入端必拒的「清单与包内容不一致」包。
                logger.warning("export_file_vanished", path=relative)
                continue
            written.append(relative)
        manifest["files"] = written
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )


async def export_archive(data_dir: Path, *, include_secrets: bool) -> str:
    """组装全量导出包到 exports/，返回 zip 文件名。"""
    db_path = data_dir / DB_ENTRY
    exports_dir = data_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = f"{EXPORT_PREFIX}{stamp}.zip"
    partial = exports_dir / f".{file_name}.part"
    snapshot = data_dir / "cache" / f"export-{stamp}-{uuid4().hex[:8]}.db"
    user_version = await read_user_version(db_path)
    await vacuum_into(db_path, snapshot)
    entries = await asyncio.to_thread(_collect_entries, data_dir, include_secrets)
    manifest: dict[str, object] = {
        "app_version": APP_VERSION,
        "db_user_version": user_version,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "include_secrets": include_secrets,
        "files": [DB_ENTRY, *entries],
    }
    try:
        await asyncio.to_thread(_build_zip, partial, snapshot, data_dir, entries, manifest)
        await asyncio.to_thread(os.replace, partial, exports_dir / file_name)
    except BaseException:
        await asyncio.to_thread(partial.unlink, missing_ok=True)
        raise
    finally:
        await asyncio.to_thread(snapshot.unlink, missing_ok=True)
    return file_name


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        raw: object = json.loads(archive.read(MANIFEST_NAME))
    except (KeyError, json.JSONDecodeError):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest.json 缺失或不是合法 JSON")
    if not isinstance(raw, dict):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest.json 结构不符")
    manifest = cast(dict[str, object], raw)
    if not isinstance(manifest.get("app_version"), str):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest 缺少 app_version")
    version = manifest.get("db_user_version")
    if isinstance(version, bool) or not isinstance(version, int):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest 缺少 db_user_version")
    if not isinstance(manifest.get("created_at"), str):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest 缺少 created_at")
    if not isinstance(manifest.get("include_secrets"), bool):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest 缺少 include_secrets")
    files = manifest.get("files")
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(item, str) for item in cast(list[object], files))
    ):
        _reject("IMPORT_ARCHIVE_INVALID", "manifest 缺少文件清单")
    return manifest


def _validate_structure(names: list[str], manifest: dict[str, object]) -> None:
    files = cast(list[str], manifest["files"])
    if DB_ENTRY not in files:
        _reject("IMPORT_ARCHIVE_INVALID", "文件清单缺少 knowrealm.db")
    if set(files) != set(names) - {MANIFEST_NAME}:
        _reject("IMPORT_ARCHIVE_INVALID", "文件清单与包内容不一致")
    for name in files:
        pure = PurePosixPath(name)
        if (
            pure.is_absolute()
            or "\\" in name
            or ":" in name
            or ".." in pure.parts
            or (name != DB_ENTRY and name.split("/", 1)[0] not in ("files", "config"))
        ):
            _reject("IMPORT_ARCHIVE_INVALID", f"文件清单包含非法路径：{name}")
    archive_version = cast(int, manifest["db_user_version"])
    supported = supported_user_version()
    if archive_version > supported:
        _reject(
            "IMPORT_ARCHIVE_VERSION_TOO_NEW",
            f"导出包数据库版本（v{archive_version}）高于当前应用（v{supported}），请先升级应用",
        )


async def _target_library_is_empty(data_dir: Path) -> bool:
    db_path = data_dir / DB_ENTRY
    if not db_path.exists():
        return True
    async with aiosqlite.connect(db_path) as connection:
        for sql in EMPTY_LIBRARY_SQL:
            try:
                row = await (await connection.execute(sql)).fetchone()
            except OperationalError:
                continue  # 旧版本库缺表视为无数据
            if row is not None:
                return False
    return True


def _land(staging: Path, data_dir: Path) -> None:
    """暂存内容落位：files/config 先行合并覆盖，db 最后原子替换。"""
    for root_name in ("files", "config"):
        source_root = staging / root_name
        if not source_root.exists():
            continue
        target_root = data_dir / root_name
        for source in sorted(source_root.rglob("*")):
            target = target_root / source.relative_to(source_root)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
    os.replace(staging / DB_ENTRY, data_dir / DB_ENTRY)


async def restore_archive(data_dir: Path, archive_path: Path) -> None:
    """开库前校验并落位导出包；校验拒绝不落盘，落位失败清理暂存。"""
    if not archive_path.is_file():
        _reject("IMPORT_ARCHIVE_MISSING", f"导出包不存在：{archive_path}")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest = _read_manifest(archive)
            _validate_structure(archive.namelist(), manifest)
    except zipfile.BadZipFile:
        _reject("IMPORT_ARCHIVE_INVALID", "不是有效的导出包")
    if not await _target_library_is_empty(data_dir):
        _reject("IMPORT_ARCHIVE_TARGET_NOT_EMPTY", "当前数据目录已有课程/记录/档案数据")

    staging = data_dir / "cache" / "import-archive"
    await asyncio.to_thread(shutil.rmtree, staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            await asyncio.to_thread(archive.extractall, staging)
        await asyncio.to_thread(_land, staging, data_dir)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, staging, ignore_errors=True)
        raise
    await asyncio.to_thread(shutil.rmtree, staging, ignore_errors=True)


async def library_is_empty(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """空库只读判断（API 侧）：无课程 + 无记录 + 无档案。"""
    async with session_factory() as session:
        for sql in EMPTY_LIBRARY_SQL:
            if (await session.execute(text(sql))).first() is not None:
                return False
    return True


def _prune_backups(backups_dir: Path) -> None:
    snapshots = sorted(
        path for path in backups_dir.glob("knowrealm-*.db") if fullmatch(BACKUP_PATTERN, path.name)
    )
    for stale in snapshots[:-KEEP_BACKUPS]:
        stale.unlink(missing_ok=True)


async def create_rolling_backup(db_path: Path, backups_dir: Path) -> Path:
    """当日快照不存在则创建；仅保留最近 KEEP_BACKUPS 份。"""
    backups_dir.mkdir(exist_ok=True)
    target = backups_dir / f"knowrealm-{datetime.now():%Y%m%d}.db"
    if not target.exists():
        await vacuum_into(db_path, target)
    await asyncio.to_thread(_prune_backups, backups_dir)
    return target
