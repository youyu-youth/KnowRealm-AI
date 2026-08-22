from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.document import AudioImportAccepted
from app.services.audio_import_service import AudioImportService

router = APIRouter(
    prefix="/api/audio-imports",
    tags=["audio-imports"],
    dependencies=[Depends(require_launch_token)],
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        507: {"model": ErrorResponse},
    },
)


@router.post("", status_code=202, response_model=AudioImportAccepted)
async def import_audio(
    request: Request,
    file: Annotated[UploadFile, File()],
    course_id: Annotated[UUID | None, Form()] = None,
    session: AsyncSession = Depends(get_db),
) -> AudioImportAccepted:
    ffmpeg_path: Path | None = request.app.state.ffmpeg_path
    if ffmpeg_path is None:
        raise HTTPException(status_code=503, detail="FFMPEG_UNAVAILABLE：音频处理组件不可用")
    return await AudioImportService.create(
        session,
        request.app.state.data_dir,
        ffmpeg_path,
        file,
        str(course_id) if course_id is not None else None,
    )
