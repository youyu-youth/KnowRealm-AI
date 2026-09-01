from fastapi import APIRouter, Depends, Request

from app.modules.capture.schemas import TextCaptureAccepted, TextCaptureCreate
from app.modules.capture.text_capture import TextCaptureService
from app.shared.deps import require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/text-captures",
    tags=["text-captures"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.post("", status_code=201, response_model=TextCaptureAccepted)
async def create_text_capture(
    body: TextCaptureCreate,
    request: Request,
) -> TextCaptureAccepted:
    return await TextCaptureService.create(
        request.app.state.session_factory,
        request.app.state.data_dir,
        body,
    )
