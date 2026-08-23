import asyncio
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import ProcessingJob, RecordingSession
from app.models.record import Record
from app.schemas.document import ProcessingJobStatus


class CacheLifecycleService:
    @staticmethod
    async def cleanup_orphans(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
    ) -> None:
        async with session_factory() as session:
            owned_record_ids = set(
                (
                    await session.scalars(
                        select(ProcessingJob.record_id)
                        .join(Record, ProcessingJob.record_id == Record.id)
                        .where(
                            Record.deleted_at.is_(None),
                            ProcessingJob.status != ProcessingJobStatus.CANCELLED,
                            ProcessingJob.record_id.is_not(None),
                        )
                    )
                ).all()
            )
            recordings = list(
                (
                    await session.scalars(
                        select(RecordingSession).where(RecordingSession.state != "DONE")
                    )
                ).all()
            )
        owned_staging: set[Path] = set()
        staging_root = (data_dir / "cache" / "staging").resolve()
        for recording in recordings:
            raw: object = json.loads(recording.chunk_paths)
            if not isinstance(raw, list):
                continue
            for value in cast(list[object], raw):
                if not isinstance(value, str):
                    continue
                path = (data_dir / Path(*PurePosixPath(value).parts)).resolve()
                if path.is_relative_to(staging_root):
                    owned_staging.add(path)

        imports_root = data_dir / "cache" / "imports"
        await asyncio.to_thread(shutil.rmtree, imports_root, ignore_errors=True)
        for name in ("audio", "sources"):
            root = data_dir / "cache" / name
            if not root.exists() or root.is_symlink() or root.is_junction():
                continue
            for candidate in root.iterdir():
                if candidate.name in owned_record_ids:
                    continue
                if candidate.is_symlink() or candidate.is_junction():
                    logger.error(
                        "cache_cleanup_unsafe_path", error_code="CACHE_CLEANUP_UNSAFE_PATH"
                    )
                    continue
                await asyncio.to_thread(shutil.rmtree, candidate, ignore_errors=True)

        if not staging_root.exists() or staging_root.is_symlink() or staging_root.is_junction():
            return
        for path in staging_root.rglob("*"):
            if path.is_file() and path.resolve() not in owned_staging:
                await asyncio.to_thread(path.unlink, missing_ok=True)
        directories = sorted(
            (path for path in staging_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                await asyncio.to_thread(directory.rmdir)
            except OSError:
                pass
