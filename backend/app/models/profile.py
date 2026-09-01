from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow
from app.schemas.profile import PrimaryRole

PROFILE_ID = "me"


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nickname: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_file: Mapped[str | None] = mapped_column(Text, default=None)
    primary_role: Mapped[PrimaryRole | None] = mapped_column(String(20), default=None)
    about_me: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
