from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.capture.capture_batch import CaptureBatchService
from app.modules.capture.schemas import CaptureBatchAccepted
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/capture-batches",
    tags=["capture-batches"],
    dependencies=[Depends(require_launch_token)],
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 409, 422, 500, 503, 507)},
)


@router.post("", status_code=202, response_model=CaptureBatchAccepted)
async def create_capture_batch(
    request: Request,
    files: Annotated[list[UploadFile] | None, File()] = None,
    course_id: Annotated[UUID | None, Form()] = None,
    recording_session_id: Annotated[UUID | None, Form()] = None,
    session: AsyncSession = Depends(get_db),
) -> CaptureBatchAccepted:
    ffmpeg_path: Path | None = request.app.state.ffmpeg_path
    if recording_session_id is not None:
        if files:
            raise HTTPException(
                status_code=400, detail="MIXED_INPUT_MODE：录音交接不能附加上传文件"
            )
        if ffmpeg_path is None:
            raise HTTPException(status_code=503, detail="FFMPEG_UNAVAILABLE：音频处理组件不可用")
        return await CaptureBatchService.create_recording(
            session,
            request.app.state.data_dir,
            ffmpeg_path,
            str(recording_session_id),
        )
    files = files or []
    if (
        any(
            Path(file.filename or "").suffix.lower() in {".mp3", ".aac", ".wav", ".m4a"}
            for file in files
        )
        and ffmpeg_path is None
    ):
        raise HTTPException(status_code=503, detail="FFMPEG_UNAVAILABLE：音频处理组件不可用")
    return await CaptureBatchService.create(
        session,
        request.app.state.data_dir,
        ffmpeg_path,
        files,
        str(course_id) if course_id is not None else None,
    )
