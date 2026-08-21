import asyncio
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import UUID

from loguru import logger
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.course import Course
from app.models.document import ProcessingJob, RecordFile, Transcript
from app.models.record import Record


class DocumentCleanupService:
    @staticmethod
    async def purge_expired(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        *,
        now: datetime | None = None,
    ) -> None:
        resolved_data_dir = data_dir.resolve()
        cutoff = (now or utcnow()) - timedelta(days=30)
        await DocumentCleanupService._recover_staged(session_factory, resolved_data_dir)
        await DocumentCleanupService._purge_orphans(session_factory, resolved_data_dir)

        async with session_factory() as session:
            record_ids = list(
                (
                    await session.execute(
                        select(Record.id)
                        .where(
                            Record.deleted_at.is_not(None),
                            Record.deleted_at < cutoff,
                        )
                        .order_by(Record.deleted_at)
                    )
                ).scalars()
            )

        for record_id in record_ids:
            await DocumentCleanupService._purge_record(
                session_factory,
                resolved_data_dir,
                record_id,
                cutoff,
            )

        async with session_factory() as session, session.begin():
            await session.execute(
                delete(Course).where(
                    Course.deleted_at.is_not(None),
                    Course.deleted_at < cutoff,
                    ~exists(select(Record.id).where(Record.course_id == Course.id)),
                )
            )

    @staticmethod
    async def _purge_record(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_id: str,
        cutoff: datetime,
    ) -> None:
        if not await DocumentCleanupService._paths_are_safe(
            session_factory,
            data_dir,
            record_id,
        ):
            return

        source_dir = data_dir / "files" / record_id
        staged_dir = data_dir / ".cleanup" / record_id / "files" / record_id
        moved = False
        if await asyncio.to_thread(source_dir.exists):
            try:
                await asyncio.to_thread(staged_dir.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(os.replace, source_dir, staged_dir)
                moved = True
            except OSError:
                logger.error(
                    "document_cleanup_file_failed",
                    error_code="DOCUMENT_CLEANUP_FILE_FAILED",
                    record_id=record_id,
                )
                return

        try:
            async with session_factory() as session, session.begin():
                record = (
                    await session.scalars(
                        select(Record).where(
                            Record.id == record_id,
                            Record.deleted_at.is_not(None),
                            Record.deleted_at < cutoff,
                        )
                    )
                ).one_or_none()
                if record is None:
                    if moved:
                        await DocumentCleanupService._restore_staged(
                            staged_dir,
                            source_dir,
                            record_id,
                        )
                    return
                await session.execute(delete(Transcript).where(Transcript.record_id == record_id))
                await session.execute(delete(RecordFile).where(RecordFile.record_id == record_id))
                await session.execute(
                    delete(ProcessingJob).where(ProcessingJob.record_id == record_id)
                )
                await session.delete(record)
        except Exception:
            if moved:
                await DocumentCleanupService._restore_staged(
                    staged_dir,
                    source_dir,
                    record_id,
                )
            logger.error(
                "document_cleanup_database_failed",
                error_code="DOCUMENT_CLEANUP_DB_FAILED",
                record_id=record_id,
            )
            return

        if moved:
            try:
                await asyncio.to_thread(shutil.rmtree, staged_dir.parent.parent)
            except OSError:
                logger.error(
                    "document_cleanup_staged_delete_failed",
                    error_code="DOCUMENT_CLEANUP_STAGED_DELETE_FAILED",
                    record_id=record_id,
                )

    @staticmethod
    async def _paths_are_safe(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_id: str,
    ) -> bool:
        prefix = f"files/{record_id}/"
        files_root = (data_dir / "files").resolve()
        record_root = (files_root / record_id).resolve()
        async with session_factory() as session:
            paths = list(
                (
                    await session.execute(
                        select(RecordFile.file_path).where(RecordFile.record_id == record_id)
                    )
                ).scalars()
            )
            active_reference = (
                await session.execute(
                    select(RecordFile.id)
                    .join(Record, RecordFile.record_id == Record.id)
                    .where(
                        RecordFile.record_id != record_id,
                        RecordFile.file_path.like(f"{prefix}%"),
                        RecordFile.deleted_at.is_(None),
                        Record.deleted_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()

        for raw_path in paths:
            path = PurePosixPath(raw_path)
            resolved_path = (data_dir / Path(*path.parts)).resolve()
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 3
                or path.parts[0] != "files"
                or path.parts[1] != record_id
                or not record_root.is_relative_to(files_root)
                or not resolved_path.is_relative_to(record_root)
            ):
                logger.error(
                    "document_cleanup_unsafe_path",
                    error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                    record_id=record_id,
                )
                return False
        if active_reference is not None:
            logger.error(
                "document_cleanup_active_path",
                error_code="DOCUMENT_CLEANUP_ACTIVE_PATH",
                record_id=record_id,
            )
            return False
        return True

    @staticmethod
    async def _restore_staged(
        staged_dir: Path,
        source_dir: Path,
        record_id: str,
    ) -> None:
        try:
            await asyncio.to_thread(source_dir.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(os.replace, staged_dir, source_dir)
            await asyncio.to_thread(shutil.rmtree, staged_dir.parent.parent, ignore_errors=True)
        except OSError:
            logger.error(
                "document_cleanup_restore_failed",
                error_code="DOCUMENT_CLEANUP_RESTORE_FAILED",
                record_id=record_id,
            )

    @staticmethod
    async def _recover_staged(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
    ) -> None:
        cleanup_root = data_dir / ".cleanup"
        if not await asyncio.to_thread(cleanup_root.exists):
            return
        staged_records = await asyncio.to_thread(lambda: list(cleanup_root.iterdir()))
        for staged_record in staged_records:
            if not staged_record.is_dir() or not DocumentCleanupService._is_uuid(
                staged_record.name
            ):
                continue
            record_id = staged_record.name
            staged_dir = staged_record / "files" / record_id
            async with session_factory() as session:
                record_exists = (
                    await session.execute(select(Record.id).where(Record.id == record_id))
                ).scalar_one_or_none()
            if record_exists is None:
                try:
                    await asyncio.to_thread(shutil.rmtree, staged_record)
                except OSError:
                    logger.error(
                        "document_cleanup_staged_delete_failed",
                        error_code="DOCUMENT_CLEANUP_STAGED_DELETE_FAILED",
                        record_id=record_id,
                    )
            elif await asyncio.to_thread(staged_dir.exists):
                await DocumentCleanupService._restore_staged(
                    staged_dir,
                    data_dir / "files" / record_id,
                    record_id,
                )

    @staticmethod
    async def _purge_orphans(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
    ) -> None:
        files_root = data_dir / "files"
        if not await asyncio.to_thread(files_root.exists):
            return
        candidates = await asyncio.to_thread(lambda: list(files_root.iterdir()))
        for candidate in candidates:
            if not candidate.is_dir() or not DocumentCleanupService._is_uuid(candidate.name):
                continue
            record_id = candidate.name
            async with session_factory() as session:
                record_exists = (
                    await session.execute(select(Record.id).where(Record.id == record_id))
                ).scalar_one_or_none()
            if record_exists is not None:
                continue
            staged_record = data_dir / ".cleanup" / record_id
            staged_dir = staged_record / "files" / record_id
            try:
                await asyncio.to_thread(staged_dir.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(os.replace, candidate, staged_dir)
                await asyncio.to_thread(shutil.rmtree, staged_record)
            except OSError:
                logger.error(
                    "document_orphan_cleanup_failed",
                    error_code="DOCUMENT_ORPHAN_CLEANUP_FAILED",
                    record_id=record_id,
                )

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            UUID(value)
        except ValueError:
            return False
        return True
