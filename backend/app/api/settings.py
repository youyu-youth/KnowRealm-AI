import asyncio

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.settings import ExternalProcessingConsentOut
from app.services.local_config import (
    external_processing_consent_at,
    grant_external_processing_consent,
)

router = APIRouter(
    prefix="/api/settings/external-processing-consents/tencent-asr",
    tags=["settings"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("", response_model=ExternalProcessingConsentOut)
async def get_tencent_asr_consent(request: Request) -> ExternalProcessingConsentOut:
    granted_at = await asyncio.to_thread(external_processing_consent_at, request.app.state.data_dir)
    return ExternalProcessingConsentOut(granted_at=granted_at)


@router.post("", response_model=ExternalProcessingConsentOut)
async def grant_tencent_asr_consent(request: Request) -> ExternalProcessingConsentOut:
    granted_at = await asyncio.to_thread(
        grant_external_processing_consent, request.app.state.data_dir
    )
    return ExternalProcessingConsentOut(granted_at=granted_at)
