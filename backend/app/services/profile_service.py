from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.profile import PROFILE_ID, Profile
from app.schemas.profile import ProfileUpdate


class ProfileService:
    @staticmethod
    async def get(session: AsyncSession) -> Profile | None:
        return await session.get(Profile, PROFILE_ID)

    @staticmethod
    async def save(session: AsyncSession, payload: ProfileUpdate) -> Profile:
        async with session.begin():
            profile = await session.get(Profile, PROFILE_ID)
            if profile is None:
                profile = Profile(id=PROFILE_ID)
                session.add(profile)
            profile.primary_role = payload.primary_role
            profile.about_me = payload.about_me
            profile.updated_at = utcnow()
            await session.flush()
            return profile
