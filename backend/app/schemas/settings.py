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
    close_behavior: Literal["TRAY", "EXIT"]
    quick_note_shortcut: str
    autostart: bool
    quiz_last_count: int


def is_valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


# 镜像 global-hotkey（Tauri global-shortcut 底层）的 accelerator 解析语法：
# 大小写不敏感、修饰键须在主键之前；此处只放行前端映射表能产出的实用键集。
_SHORTCUT_MODIFIERS = frozenset(
    {
        "CTRL",
        "CONTROL",
        "ALT",
        "OPTION",
        "SHIFT",
        "SUPER",
        "CMD",
        "COMMAND",
        "COMMANDORCONTROL",
        "COMMANDORCTRL",
        "CMDORCTRL",
        "CMDORCONTROL",
    }
)
_SHORTCUT_KEYS = frozenset(
    {chr(code) for code in range(ord("A"), ord("Z") + 1)}
    | {str(digit) for digit in range(10)}
    | {f"F{index}" for index in range(1, 25)}
    | {
        "BACKQUOTE",
        "BACKSLASH",
        "BRACKETLEFT",
        "BRACKETRIGHT",
        "COMMA",
        "EQUAL",
        "MINUS",
        "PERIOD",
        "QUOTE",
        "SEMICOLON",
        "SLASH",
        "SPACE",
        "TAB",
        "CAPSLOCK",
        "ENTER",
        "BACKSPACE",
        "DELETE",
        "END",
        "HOME",
        "INSERT",
        "PAGEDOWN",
        "PAGEUP",
        "PRINTSCREEN",
        "SCROLLLOCK",
        "PAUSE",
        "ARROWDOWN",
        "ARROWLEFT",
        "ARROWRIGHT",
        "ARROWUP",
        "NUMLOCK",
    }
)


def is_valid_shortcut(value: str) -> bool:
    """至少一个修饰键在前 + 恰一个白名单主键，且可被 Tauri global-shortcut 解析。"""
    tokens = [token.strip().upper() for token in value.split("+")]
    if "" in tokens:
        return False
    *modifiers, key = tokens
    if not modifiers:
        return False
    return key in _SHORTCUT_KEYS and all(token in _SHORTCUT_MODIFIERS for token in modifiers)


class PreferencesUpdate(BaseModel):
    """全字段 optional 的部分更新：未提供的键保持原值；timezone 显式 null 表示跟随系统。"""

    theme: Literal["LIGHT", "DARK", "SYSTEM"] | None = Field(default=None, description="外观主题")
    font_scale: Literal["S", "M", "L"] | None = Field(default=None, description="字号档位")
    timezone: str | None = Field(default=None, description="IANA 时区名；null 表示跟随系统")
    close_behavior: Literal["TRAY", "EXIT"] | None = Field(default=None, description="关窗行为")
    quick_note_shortcut: str | None = Field(default=None, description="速记快捷键 accelerator")
    autostart: bool | None = Field(default=None, description="开机自启")
    quiz_last_count: Literal[3, 5, 10] | None = Field(default=None, description="习题生成档位偏好")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_timezone(value):
            raise ValueError("timezone 必须是合法的 IANA 时区名")
        return value

    @field_validator("quick_note_shortcut")
    @classmethod
    def validate_quick_note_shortcut(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_shortcut(value):
            raise ValueError(
                "quick_note_shortcut 必须是至少一个修饰键（Ctrl/Alt/Shift/Super）"
                "加一个主键的合法组合"
            )
        return value

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        for field in (
            "theme",
            "font_scale",
            "close_behavior",
            "quick_note_shortcut",
            "autostart",
            "quiz_last_count",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不接受 null")
        return self
