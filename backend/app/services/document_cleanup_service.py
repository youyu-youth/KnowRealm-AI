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
        resolved_data_dir = await asyncio.to_thread(data_dir.resolve)
        files_root, cleanup_root = await asyncio.gather(
            DocumentCleanupService._managed_directory(
                resolved_data_dir / "files",
                resolved_data_dir,
            ),
            DocumentCleanupService._managed_directory(
                resolved_data_dir / ".cleanup",
                resolved_data_dir,
            ),
        )
        if files_root is None or cleanup_root is None:
            logger.error(
                "document_cleanup_unsafe_root",
                error_code="DOCUMENT_CLEANUP_UNSAFE_ROOT",
            )
            return
        cutoff = (now or utcnow()) - timedelta(days=30)
        await DocumentCleanupService._recover_staged(
            session_factory,
            files_root,
            cleanup_root,
        )
        async with session_factory() as session:
            active_paths = list(
                (
                    await session.execute(
                        select(RecordFile.file_path)
                        .join(Record, RecordFile.record_id == Record.id)
                        .where(
                            RecordFile.deleted_at.is_(None),
                            Record.deleted_at.is_(None),
                        )
                    )
                ).scalars()
            )
        resolved_active_paths = await asyncio.to_thread(
            lambda: [
                (resolved_data_dir / Path(*PurePosixPath(raw).parts)).resolve()
                for raw in active_paths
            ]
        )
        active_target_record_ids: set[str] = set()
        for path in resolved_active_paths:
            if not path.is_relative_to(files_root):
                continue
            relative_parts = path.relative_to(files_root).parts
            if relative_parts and DocumentCleanupService._is_uuid(relative_parts[0]):
                active_target_record_ids.add(relative_parts[0])
        active_targets = frozenset(active_target_record_ids)
        await DocumentCleanupService._purge_orphans(
            session_factory,
            files_root,
            cleanup_root,
            active_targets,
        )

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
                files_root,
                cleanup_root,
                active_targets,
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
        files_root: Path,
        cleanup_root: Path,
        active_targets: frozenset[str],
        record_id: str,
        cutoff: datetime,
    ) -> None:
        if not await DocumentCleanupService._paths_are_safe(
            session_factory,
            data_dir,
            files_root,
            active_targets,
            record_id,
        ):
            return

        source_dir = files_root / record_id
        staged_record = cleanup_root / record_id
        staged_dir = staged_record / "files" / record_id
        if (
            await DocumentCleanupService._managed_directory(staged_record, cleanup_root) is None
            or await DocumentCleanupService._managed_directory(staged_dir, staged_record) is None
        ):
            logger.error(
                "document_cleanup_unsafe_path",
                error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                record_id=record_id,
            )
            return
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
        files_root: Path,
        active_targets: frozenset[str],
        record_id: str,
    ) -> bool:
        record_root = await DocumentCleanupService._managed_directory(
            files_root / record_id,
            files_root,
        )
        if record_root is None:
            logger.error(
                "document_cleanup_unsafe_path",
                error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                record_id=record_id,
            )
            return False
        async with session_factory() as session:
            paths = list(
                (
                    await session.execute(
                        select(RecordFile.file_path).where(RecordFile.record_id == record_id)
                    )
                ).scalars()
            )

        resolved_paths = await asyncio.to_thread(
            lambda: [
                (PurePosixPath(raw), (data_dir / Path(*PurePosixPath(raw).parts)).resolve())
                for raw in paths
            ]
        )
        for path, resolved_path in resolved_paths:
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 3
                or path.parts[0] != "files"
                or path.parts[1] != record_id
                or not resolved_path.is_relative_to(record_root)
            ):
                logger.error(
                    "document_cleanup_unsafe_path",
                    error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                    record_id=record_id,
                )
                return False
        if record_id in active_targets:
            logger.error(
                "document_cleanup_active_path",
                error_code="DOCUMENT_CLEANUP_ACTIVE_PATH",
                record_id=record_id,
            )
            return False
        return True

    @staticmethod
    async def _managed_directory(path: Path, root: Path) -> Path | None:
        return await asyncio.to_thread(
            DocumentCleanupService._resolve_managed_directory,
            path,
            root,
        )

    @staticmethod
    def _resolve_managed_directory(path: Path, root: Path) -> Path | None:
        if path.is_symlink() or path.is_junction():
            return None
        resolved = path.resolve()
        return resolved if resolved.is_relative_to(root) else None

    @staticmethod
    def _list_uuid_directories(root: Path) -> tuple[list[Path], list[str]]:
        safe: list[Path] = []
        unsafe: list[str] = []
        for candidate in root.iterdir():
            if not DocumentCleanupService._is_uuid(candidate.name):
                continue
            resolved = DocumentCleanupService._resolve_managed_directory(candidate, root)
            if resolved is None or not candidate.is_dir():
                unsafe.append(candidate.name)
            else:
                safe.append(resolved)
        return safe, unsafe

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
        files_root: Path,
        cleanup_root: Path,
    ) -> None:
        if not await asyncio.to_thread(cleanup_root.exists):
            return
        staged_records, unsafe_records = await asyncio.to_thread(
            DocumentCleanupService._list_uuid_directories,
            cleanup_root,
        )
        for record_id in unsafe_records:
            logger.error(
                "document_cleanup_unsafe_path",
                error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                record_id=record_id,
            )
        for staged_record in staged_records:
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
            elif await DocumentCleanupService._managed_directory(staged_dir, staged_record) is None:
                logger.error(
                    "document_cleanup_unsafe_path",
                    error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                    record_id=record_id,
                )
            elif await asyncio.to_thread(staged_dir.exists):
                await DocumentCleanupService._restore_staged(
                    staged_dir,
                    files_root / record_id,
                    record_id,
                )

    @staticmethod
    async def _purge_orphans(
        session_factory: async_sessionmaker[AsyncSession],
        files_root: Path,
        cleanup_root: Path,
        active_targets: frozenset[str],
    ) -> None:
        if not await asyncio.to_thread(files_root.exists):
            return
        candidates, unsafe_candidates = await asyncio.to_thread(
            DocumentCleanupService._list_uuid_directories,
            files_root,
        )
        for record_id in unsafe_candidates:
            logger.error(
                "document_cleanup_unsafe_path",
                error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                record_id=record_id,
            )
        for candidate in candidates:
            record_id = candidate.name
            if record_id in active_targets:
                logger.error(
                    "document_cleanup_active_path",
                    error_code="DOCUMENT_CLEANUP_ACTIVE_PATH",
                    record_id=record_id,
                )
                continue
            async with session_factory() as session:
                record_exists = (
                    await session.execute(select(Record.id).where(Record.id == record_id))
                ).scalar_one_or_none()
            if record_exists is not None:
                continue
            staged_record = cleanup_root / record_id
            staged_dir = staged_record / "files" / record_id
            if (
                await DocumentCleanupService._managed_directory(staged_record, cleanup_root) is None
                or await DocumentCleanupService._managed_directory(staged_dir, staged_record)
                is None
            ):
                logger.error(
                    "document_cleanup_unsafe_path",
                    error_code="DOCUMENT_CLEANUP_UNSAFE_PATH",
                    record_id=record_id,
                )
                continue
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
