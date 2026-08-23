from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


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
