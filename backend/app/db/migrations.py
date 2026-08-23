from pathlib import Path
from re import fullmatch
from typing import cast

import aiosqlite

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def run_migrations(db_path: Path) -> None:
    migrations: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = fullmatch(r"(\d{4})_[a-z0-9_]+\.sql", path.name)
        if match is None:
            raise RuntimeError(f"迁移文件名无效: {path.name}")
        migrations.append((int(match.group(1)), path))

    expected_versions = list(range(1, len(migrations) + 1))
    if [version for version, _ in migrations] != expected_versions:
        raise RuntimeError("迁移编号必须从 0001 连续递增")

    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("PRAGMA journal_mode=WAL")
        row = await (await connection.execute("PRAGMA user_version")).fetchone()
        if row is None:
            raise RuntimeError("无法读取数据库版本")
        current = cast(int, row[0])
        if current > len(migrations):
            raise RuntimeError("数据库版本高于当前 sidecar 支持的版本")

        for version, path in migrations:
            if version <= current:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                await connection.execute("PRAGMA foreign_keys=OFF")
                await connection.executescript(
                    f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version={version};\nCOMMIT;"
                )
                await connection.execute("PRAGMA foreign_keys=ON")
                violations = await (await connection.execute("PRAGMA foreign_key_check")).fetchall()
                if violations:
                    raise RuntimeError(f"迁移 {version:04d} 产生外键错误")
            except Exception:
                await connection.rollback()
                await connection.execute("PRAGMA foreign_keys=ON")
                raise
