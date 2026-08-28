from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrimaryRole(StrEnum):
    STUDENT = "STUDENT"
    DEVELOPER = "DEVELOPER"
    OFFICE_WORKER = "OFFICE_WORKER"
    OTHER = "OTHER"


class ProfileOut(BaseModel):
    """档案读取/保存结果，只暴露角色与自我介绍；未建档时字段均为 None（空档案语义）。"""

    model_config = ConfigDict(from_attributes=True)

    primary_role: PrimaryRole | None = Field(default=None, description="用户角色，未建档为空")
    about_me: str | None = Field(default=None, description="自我介绍，未建档为空")


class ProfileUpdate(BaseModel):
    primary_role: PrimaryRole = Field(description="角色四选一")
    about_me: str | None = Field(
        default=None,
        max_length=200,
        description="自我介绍，≤200 字，空白视为未填写",
    )

    @field_validator("about_me")
    @classmethod
    def clean_about_me(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None
