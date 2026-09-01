from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profile.schemas import ProfileOut, ProfileUpdate
from app.modules.profile.service import ProfileService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

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


avatar_responses: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorResponse, "description": "头像超过 2MB"},
}


@router.get(
    "/avatar",
    responses={404: {"model": ErrorResponse, "description": "未设置头像"}},
)
async def read_avatar(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    content, media_type = await ProfileService.read_avatar(
        session,
        request.app.state.data_dir,
    )
    # 覆盖上传后同 URL 内容会变，禁用缓存避免读到旧头像。
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.put("/avatar", status_code=204, responses=avatar_responses)
async def put_avatar(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> None:
    content = await request.body()
    await ProfileService.save_avatar(session, request.app.state.data_dir, content)


@router.delete("/avatar", status_code=204)
async def delete_avatar(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> None:
    await ProfileService.delete_avatar(session, request.app.state.data_dir)
