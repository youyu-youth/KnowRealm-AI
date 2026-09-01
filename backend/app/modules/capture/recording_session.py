import asyncio
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.db.base import utcnow
from app.modules.capture.audio_import import copy_upload
from app.modules.capture.models import RecordingSession
from app.modules.capture.recording import (
    RecordingChunkAccepted,
    RecordingChunkTargetState,
    RecordingSessionCreate,
    RecordingSessionOut,
    RecordingSessionTargetState,
)
from app.modules.capture.schemas import RecordingSessionState
from app.modules.course.schemas import CourseStatus
from app.modules.course.service import CourseService

RECORDING_BITRATE_BPS = 128_000
MAX_RECORDING_DURATION_MS = 3 * 60 * 60 * 1000
INITIAL_DISK_RESERVE_BYTES = RECORDING_BITRATE_BPS * MAX_RECORDING_DURATION_MS // 8 // 1000 * 2
POC_CHUNK_DURATION_MS = 20_000
NEXT_CHUNK_RESERVE_BYTES = RECORDING_BITRATE_BPS * POC_CHUNK_DURATION_MS // 8 // 1000 * 2
MAX_WEBM_CHUNK_BYTES = 16 * 1024 * 1024

_CREATE_LOCK = asyncio.Lock()
_APPEND_LOCK = asyncio.Lock()


def _chunk_paths(recording: RecordingSession) -> list[str]:
    raw: object = json.loads(recording.chunk_paths)
    if not isinstance(raw, list):
        raise HTTPException(status_code=500, detail="INVALID_RECORDING_SESSION：录音清单损坏")
    values = cast(list[object], raw)
    if not all(isinstance(value, str) for value in values):
        raise HTTPException(status_code=500, detail="INVALID_RECORDING_SESSION：录音清单损坏")
    return cast(list[str], values)


def _to_out(recording: RecordingSession) -> RecordingSessionOut:
    return RecordingSessionOut(
        id=recording.id,
        course_id=recording.course_id,
        title=recording.title or "录音",
        started_at=recording.started_at,
        updated_at=recording.updated_at,
        state=recording.state,
        recorded_duration_ms=recording.recorded_duration_ms,
        chunk_count=len(_chunk_paths(recording)),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_webm(path: Path) -> bool:
    with path.open("rb") as source:
        return source.read(4) == b"\x1aE\xdf\xa3"


class RecordingSessionService:
    @staticmethod
    async def create(
        session: AsyncSession,
        data_dir: Path,
        payload: RecordingSessionCreate,
    ) -> RecordingSessionOut:
        # ponytail: one sidecar writer; use a DB claim only if writers become multi-process.
        async with _CREATE_LOCK:
            active = await session.scalar(
                select(RecordingSession.id).where(
                    RecordingSession.state.in_(
                        (RecordingSessionState.RECORDING, RecordingSessionState.PAUSED)
                    )
                )
            )
            if active is not None:
                raise HTTPException(status_code=409, detail="RECORDING_ACTIVE：已有录音会话")

            course_id = str(payload.course_id) if payload.course_id is not None else None
            course = await CourseService.get(session, course_id) if course_id is not None else None
            if course_id is not None and course is None:
                raise HTTPException(status_code=404, detail="课程不存在或已删除")
            if course is not None and course.status != CourseStatus.ACTIVE:
                raise HTTPException(status_code=409, detail="已归档课程不能接受新录音")
            await session.rollback()

            free = (await asyncio.to_thread(shutil.disk_usage, data_dir)).free
            if free < INITIAL_DISK_RESERVE_BYTES:
                raise HTTPException(status_code=507, detail="INSUFFICIENT_DISK：数据目录空间不足")

            started_at = utcnow()
            recording = RecordingSession(
                id=str(uuid4()),
                course_id=course_id,
                title=payload.title
                or f"录音 {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}",
                started_at=started_at,
                updated_at=started_at,
                state=RecordingSessionState.RECORDING,
                chunk_paths="[]",
                recorded_duration_ms=0,
            )
            async with session.begin():
                session.add(recording)
                await session.flush()
            return _to_out(recording)

    @staticmethod
    async def list_unfinished(session: AsyncSession) -> list[RecordingSessionOut]:
        recordings = list(
            (
                await session.scalars(
                    select(RecordingSession)
                    .where(RecordingSession.state != RecordingSessionState.DONE)
                    .order_by(RecordingSession.started_at)
                )
            ).all()
        )
        return [_to_out(recording) for recording in recordings]

    @staticmethod
    async def append_chunk(
        session: AsyncSession,
        data_dir: Path,
        recording_session_id: str,
        sequence_no: int,
        duration_ms: int,
        target_state: RecordingChunkTargetState,
        upload: UploadFile,
    ) -> RecordingChunkAccepted:
        async with _APPEND_LOCK:
            recording = await session.get(RecordingSession, recording_session_id)
            if recording is None:
                raise HTTPException(status_code=404, detail="RECORDING_NOT_FOUND：录音会话不存在")
            paths = _chunk_paths(recording)
            if sequence_no > len(paths):
                raise HTTPException(status_code=409, detail="RECORDING_CHUNK_ORDER：录音分片乱序")
            if sequence_no == len(paths) and recording.state != RecordingSessionState.RECORDING:
                raise HTTPException(
                    status_code=409, detail="RECORDING_NOT_ACTIVE：录音会话不可追加"
                )
            if (
                sequence_no == len(paths)
                and recording.recorded_duration_ms + duration_ms > MAX_RECORDING_DURATION_MS
            ):
                raise HTTPException(status_code=409, detail="RECORDING_TOO_LONG：录音超过 3 小时")
            await session.rollback()

            staging_root = (data_dir / "cache" / "staging").resolve()
            session_dir = staging_root / recording_session_id
            if not session_dir.is_relative_to(staging_root):
                raise HTTPException(
                    status_code=400, detail="INVALID_RECORDING_STAGING：暂存路径无效"
                )
            if session_dir.exists() and (session_dir.is_symlink() or session_dir.is_junction()):
                raise HTTPException(
                    status_code=400, detail="INVALID_RECORDING_STAGING：暂存路径不安全"
                )
            session_dir.mkdir(parents=True, exist_ok=True)
            temporary_path = session_dir / f".{uuid4()}.part"
            try:
                size, content_hash = await asyncio.to_thread(
                    copy_upload, upload.file, temporary_path
                )
                if size == 0:
                    raise HTTPException(
                        status_code=400, detail="EMPTY_RECORDING_CHUNK：录音分片为空"
                    )
                if size > MAX_WEBM_CHUNK_BYTES:
                    raise HTTPException(
                        status_code=400, detail="RECORDING_CHUNK_TOO_LARGE：录音分片过大"
                    )
                if not await asyncio.to_thread(_is_webm, temporary_path):
                    raise HTTPException(status_code=400, detail="INVALID_WEBM：录音分片不是 WebM")

                if sequence_no < len(paths):
                    existing = (data_dir / paths[sequence_no]).resolve()
                    if (
                        not existing.is_relative_to(staging_root)
                        or not existing.is_file()
                        or await asyncio.to_thread(_sha256_file, existing) != content_hash
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="RECORDING_CHUNK_CONFLICT：同序号分片内容不同",
                        )
                    current = await session.get(RecordingSession, recording_session_id)
                    if current is None:
                        raise HTTPException(
                            status_code=404, detail="RECORDING_NOT_FOUND：录音会话不存在"
                        )
                    return RecordingChunkAccepted(
                        session=_to_out(current),
                        sequence_no=sequence_no,
                        content_hash=content_hash,
                        can_continue=current.state == RecordingSessionState.RECORDING,
                    )

                final_path = session_dir / f"{sequence_no:04d}.webm"
                await asyncio.to_thread(os.replace, temporary_path, final_path)
                relative_path = final_path.relative_to(data_dir).as_posix()
                free = (await asyncio.to_thread(shutil.disk_usage, session_dir)).free
                can_continue = free >= NEXT_CHUNK_RESERVE_BYTES
                final_state = (
                    target_state
                    if target_state != RecordingChunkTargetState.RECORDING or can_continue
                    else RecordingChunkTargetState.PAUSED
                )
                try:
                    async with session.begin():
                        current = await session.get(RecordingSession, recording_session_id)
                        if current is None:
                            raise HTTPException(
                                status_code=404,
                                detail="RECORDING_NOT_FOUND：录音会话不存在",
                            )
                        current_paths = _chunk_paths(current)
                        if (
                            current.state != RecordingSessionState.RECORDING
                            or len(current_paths) != sequence_no
                        ):
                            raise HTTPException(
                                status_code=409,
                                detail="RECORDING_CHUNK_ORDER：录音分片状态已改变",
                            )
                        current_paths.append(relative_path)
                        current.chunk_paths = json.dumps(current_paths)
                        current.recorded_duration_ms += duration_ms
                        current.state = RecordingSessionState(final_state.value)
                        current.updated_at = utcnow()
                        await session.flush()
                except BaseException:
                    await asyncio.to_thread(final_path.unlink, missing_ok=True)
                    raise
                return RecordingChunkAccepted(
                    session=_to_out(current),
                    sequence_no=sequence_no,
                    content_hash=content_hash,
                    can_continue=can_continue and current.state == RecordingSessionState.RECORDING,
                )
            finally:
                await asyncio.to_thread(temporary_path.unlink, missing_ok=True)

    @staticmethod
    async def update_state(
        session: AsyncSession,
        data_dir: Path,
        recording_session_id: str,
        target_state: RecordingSessionTargetState,
    ) -> RecordingSessionOut:
        if target_state == RecordingSessionTargetState.RECORDING:
            free = (await asyncio.to_thread(shutil.disk_usage, data_dir)).free
            if free < NEXT_CHUNK_RESERVE_BYTES:
                raise HTTPException(status_code=507, detail="INSUFFICIENT_DISK：数据目录空间不足")
        async with session.begin():
            recording = await session.get(RecordingSession, recording_session_id)
            if recording is None:
                raise HTTPException(status_code=404, detail="RECORDING_NOT_FOUND：录音会话不存在")
            if target_state == RecordingSessionTargetState.RECORDING:
                if recording.state not in (
                    RecordingSessionState.PAUSED,
                    RecordingSessionState.RECORDING,
                ):
                    raise HTTPException(
                        status_code=409, detail="RECORDING_NOT_PAUSED：录音会话不可继续"
                    )
                recording.state = RecordingSessionState.RECORDING
            else:
                if recording.state not in (
                    RecordingSessionState.RECORDING,
                    RecordingSessionState.PAUSED,
                    RecordingSessionState.FINALIZING,
                ):
                    raise HTTPException(
                        status_code=409, detail="RECORDING_NOT_PAUSED：请先保存当前录音分片"
                    )
                if not _chunk_paths(recording):
                    raise HTTPException(status_code=400, detail="EMPTY_RECORDING：录音没有分片")
                recording.state = RecordingSessionState.FINALIZING
            recording.updated_at = utcnow()
            await session.flush()
        return _to_out(recording)

    @staticmethod
    async def abandon(
        session: AsyncSession,
        data_dir: Path,
        recording_session_id: str,
    ) -> None:
        recording = await session.get(RecordingSession, recording_session_id)
        if recording is None:
            raise HTTPException(status_code=404, detail="RECORDING_NOT_FOUND：录音会话不存在")
        if recording.state not in (RecordingSessionState.RECORDING, RecordingSessionState.PAUSED):
            raise HTTPException(status_code=409, detail="RECORDING_SEALED：已封口录音不能放弃")
        await session.rollback()

        staging_root = (data_dir / "cache" / "staging").resolve()
        session_dir = staging_root / recording_session_id
        discarded_dir = staging_root / f".{recording_session_id}.discarding"
        if session_dir.exists():
            await asyncio.to_thread(os.replace, session_dir, discarded_dir)
        try:
            async with session.begin():
                current = await session.get(RecordingSession, recording_session_id)
                if current is None:
                    raise HTTPException(
                        status_code=404, detail="RECORDING_NOT_FOUND：录音会话不存在"
                    )
                await session.delete(current)
        except BaseException:
            if discarded_dir.exists():
                await asyncio.to_thread(os.replace, discarded_dir, session_dir)
            raise
        await asyncio.to_thread(shutil.rmtree, discarded_dir, ignore_errors=True)
