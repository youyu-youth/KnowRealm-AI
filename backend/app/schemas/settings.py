from typing import Literal, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class ExternalProcessingConsentOut(BaseModel):
    granted_at: str | None


class LlmProviderUpdate(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    clear_api_key: bool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Provider 地址必须是 HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Provider 地址不能包含用户名或密码")
        return normalized

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型名不能为空")
        return normalized


class LlmProviderOut(BaseModel):
    base_url: str
    model: str
    has_api_key: bool
    api_key_hint: str | None


class LlmProviderStateOut(BaseModel):
    provider: LlmProviderOut | None


class LlmConsentOut(BaseModel):
    granted_at: str | None
    current: bool


class PreferencesOut(BaseModel):
    theme: Literal["LIGHT", "DARK", "SYSTEM"]
    font_scale: Literal["S", "M", "L"]
    timezone: str | None
    quiz_last_count: int


def is_valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


class PreferencesUpdate(BaseModel):
    """全字段 optional 的部分更新：未提供的键保持原值；timezone 显式 null 表示跟随系统。"""

    theme: Literal["LIGHT", "DARK", "SYSTEM"] | None = Field(default=None, description="外观主题")
    font_scale: Literal["S", "M", "L"] | None = Field(default=None, description="字号档位")
    timezone: str | None = Field(default=None, description="IANA 时区名；null 表示跟随系统")
    quiz_last_count: Literal[3, 5, 10] | None = Field(default=None, description="习题生成档位偏好")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_timezone(value):
            raise ValueError("timezone 必须是合法的 IANA 时区名")
        return value

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        for field in ("theme", "font_scale", "quiz_last_count"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不接受 null")
        return self
