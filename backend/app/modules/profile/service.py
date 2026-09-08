import asyncio
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.profile.models import PROFILE_ID, Profile
from app.modules.profile.schemas import ProfileUpdate
from app.shared.errors import CodedHTTPException

AVATAR_MAX_BYTES = 2 * 1024 * 1024

# 魔数 → (扩展名, 媒体类型)；只收 PNG/JPG/WebP，GIF/BMP 明确不收。
_AVATAR_KINDS: dict[bytes, tuple[str, str]] = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
}
AVATAR_EXTENSIONS = ("png", "jpg", "webp")
AVATAR_MEDIA_TYPES: dict[str, str] = {
    **{ext: media for ext, media in _AVATAR_KINDS.values()},
    "webp": "image/webp",
}


def _sniff_avatar(content: bytes) -> tuple[str, str]:
    for magic, kind in _AVATAR_KINDS.items():
        if content.startswith(magic):
            return kind
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ("webp", "image/webp")
    raise CodedHTTPException(
        code="AVATAR_FORMAT_UNSUPPORTED", status_code=422, detail="头像仅支持 PNG/JPG/WebP 格式"
    )


class ProfileService:
    @staticmethod
    async def get(session: AsyncSession) -> Profile | None:
        return await session.get(Profile, PROFILE_ID)

    @staticmethod
    async def save(session: AsyncSession, payload: ProfileUpdate) -> Profile:
        async with session.begin():
            profile = await ProfileService._editable(session)
            profile.primary_role = payload.primary_role
            profile.nickname = payload.nickname
            profile.about_me = payload.about_me
            profile.updated_at = utcnow()
            await session.flush()
            return profile

    @staticmethod
    async def save_avatar(session: AsyncSession, data_dir: Path, content: bytes) -> None:
        if len(content) > AVATAR_MAX_BYTES:
            raise CodedHTTPException(
                code="AVATAR_TOO_LARGE", status_code=413, detail="头像文件不能超过 2MB"
            )
        ext, _ = _sniff_avatar(content)
        files_dir = data_dir / "files"

        def _write_file() -> None:
            files_dir.mkdir(exist_ok=True)
            # 覆盖式：换格式上传时清掉其它扩展名的旧头像，files/ 只保留一份。
            for other in AVATAR_EXTENSIONS:
                if other != ext:
                    (files_dir / f"avatar.{other}").unlink(missing_ok=True)
            # 先写 cache/ 临时文件再原子替换：files/ 不出现部分写入（导出遍历无竞态）。
            temporary = data_dir / "cache" / "imports" / f"avatar-{uuid4().hex}.tmp"
            temporary.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(content)
            os.replace(temporary, files_dir / f"avatar.{ext}")

        await asyncio.to_thread(_write_file)
        relative = f"files/avatar.{ext}"
        async with session.begin():
            profile = await ProfileService._editable(session)
            profile.avatar_file = relative
            profile.updated_at = utcnow()
            await session.flush()

    @staticmethod
    async def read_avatar(session: AsyncSession, data_dir: Path) -> tuple[bytes, str]:
        profile = await session.get(Profile, PROFILE_ID)
        relative = profile.avatar_file if profile is not None else None
        if relative is None:
            raise CodedHTTPException(code="AVATAR_NOT_SET", status_code=404, detail="未设置头像")
        path = data_dir / relative
        ext = path.suffix.lstrip(".")
        if ext not in AVATAR_MEDIA_TYPES:
            raise CodedHTTPException(code="AVATAR_NOT_SET", status_code=404, detail="未设置头像")
        try:
            content = await asyncio.to_thread(path.read_bytes)
        except OSError:
            raise CodedHTTPException(
                code="AVATAR_NOT_SET", status_code=404, detail="未设置头像"
            ) from None
        return content, AVATAR_MEDIA_TYPES[ext]

    @staticmethod
    async def delete_avatar(session: AsyncSession, data_dir: Path) -> None:
        def _delete_files() -> None:
            for ext in AVATAR_EXTENSIONS:
                (data_dir / "files" / f"avatar.{ext}").unlink(missing_ok=True)

        await asyncio.to_thread(_delete_files)
        async with session.begin():
            profile = await session.get(Profile, PROFILE_ID)
            if profile is not None and profile.avatar_file is not None:
                profile.avatar_file = None
                profile.updated_at = utcnow()
                await session.flush()

    @staticmethod
    async def _editable(session: AsyncSession) -> Profile:
        profile = await session.get(Profile, PROFILE_ID)
        if profile is None:
            profile = Profile(id=PROFILE_ID)
            session.add(profile)
        return profile
