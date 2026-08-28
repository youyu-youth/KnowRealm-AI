from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter(
    prefix="/api/profile",
    tags=["profile"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("", response_model=ProfileOut)
async def read_profile(session: AsyncSession = Depends(get_db)) -> ProfileOut:
    profile = await ProfileService.get(session)
    if profile is None:
        return ProfileOut()
    return ProfileOut.model_validate(profile)


@router.put("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    session: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await ProfileService.save(session, payload)
    return ProfileOut.model_validate(profile)
