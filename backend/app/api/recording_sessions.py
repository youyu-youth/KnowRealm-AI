from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recording import (
    RecordingChunkAccepted,
    RecordingChunkTargetState,
    RecordingSessionCreate,
    RecordingSessionOut,
    RecordingSessionUpdate,
)
from app.services.recording_session_service import RecordingSessionService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/recording-sessions",
    tags=["recording-sessions"],
    dependencies=[Depends(require_launch_token)],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 409, 422, 500, 507)},
)


@router.post("", status_code=201, response_model=RecordingSessionOut)
async def create_recording_session(
    request: Request,
    payload: RecordingSessionCreate,
    session: AsyncSession = Depends(get_db),
) -> RecordingSessionOut:
    return await RecordingSessionService.create(session, request.app.state.data_dir, payload)


@router.get("", response_model=list[RecordingSessionOut])
async def list_recording_sessions(
    session: AsyncSession = Depends(get_db),
) -> list[RecordingSessionOut]:
    return await RecordingSessionService.list_unfinished(session)


@router.post(
    "/{recording_session_id}/chunks", status_code=201, response_model=RecordingChunkAccepted
)
async def append_recording_chunk(
    request: Request,
    recording_session_id: UUID,
    file: Annotated[UploadFile, File()],
    sequence_no: Annotated[int, Form(ge=0)],
    duration_ms: Annotated[int, Form(ge=1, le=300_000)],
    target_state: Annotated[RecordingChunkTargetState, Form()],
    session: AsyncSession = Depends(get_db),
) -> RecordingChunkAccepted:
    return await RecordingSessionService.append_chunk(
        session,
        request.app.state.data_dir,
        str(recording_session_id),
        sequence_no,
        duration_ms,
        target_state,
        file,
    )


@router.patch("/{recording_session_id}", response_model=RecordingSessionOut)
async def update_recording_session(
    request: Request,
    recording_session_id: UUID,
    payload: RecordingSessionUpdate,
    session: AsyncSession = Depends(get_db),
) -> RecordingSessionOut:
    return await RecordingSessionService.update_state(
        session,
        request.app.state.data_dir,
        str(recording_session_id),
        payload.target_state,
    )


@router.delete("/{recording_session_id}", status_code=204, response_class=Response)
async def abandon_recording_session(
    request: Request,
    recording_session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await RecordingSessionService.abandon(
        session,
        request.app.state.data_dir,
        str(recording_session_id),
    )
    return Response(status_code=204)
