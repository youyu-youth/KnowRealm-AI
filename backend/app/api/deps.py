from collections.abc import AsyncIterator
from hmac import compare_digest

from fastapi import Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def require_launch_token(
    request: Request,
    x_knowrealm_token: str | None = Header(default=None),
) -> None:
    expected = request.app.state.launch_token
    if x_knowrealm_token is None or not compare_digest(x_knowrealm_token, expected):
        raise HTTPException(status_code=403, detail="无权访问本地服务")


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session
