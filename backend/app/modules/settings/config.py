import json
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from hashlib import sha256
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from app.modules.settings.schemas import QUIZ_COUNT_CHOICES, is_valid_shortcut, is_valid_timezone


@dataclass(frozen=True)
class TencentAsrConfig:
    secret_id: str
    secret_key: str
    region: str


@dataclass(frozen=True)
class LlmProviderConfig:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class WebSearchProviderConfig:
    provider: str
    api_key: str


# web_search 供应商本期只认 tavily；provider 字段为博查/智谱预留（spec 根决策 2）。
WEB_SEARCH_PROVIDER_CHOICES = ("tavily",)


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 带 pid+线程 id 避免并发写共用同名临时文件互相截断；仍以 .tmp 结尾供导出排除。
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
    # Windows 下替换需删除目标；并发读（llm_consent 等）或杀软瞬持句柄会报
    # WinError 5，读方毫秒级释放，短退避重试即可恢复。
    for delay in (0.05, 0.1, 0.2, 0.4):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(delay)
    os.replace(temporary, path)


def external_processing_consent_at(data_dir: Path) -> str | None:
    value = _read_json(data_dir / "config" / "settings.json").get("tencent_asr_consent_granted_at")
    return value if isinstance(value, str) and value else None


def grant_external_processing_consent(data_dir: Path) -> str:
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    granted_at = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    settings["tencent_asr_consent_granted_at"] = granted_at
    _write_json(path, settings)
    return granted_at


def load_tencent_asr_provider(data_dir: Path) -> TencentAsrConfig | None:
    """按 providers.json 事实返回（允许空密钥），供设置页读写使用。"""
    raw = _read_json(data_dir / "config" / "providers.json").get("tencent_asr")
    if not isinstance(raw, dict):
        return None
    provider = cast(dict[str, object], raw)
    secret_id = provider.get("secret_id")
    secret_key = provider.get("secret_key")
    region = provider.get("region")
    if not all(isinstance(value, str) for value in (secret_id, secret_key, region)):
        return None
    return TencentAsrConfig(
        secret_id=cast(str, secret_id),
        secret_key=cast(str, secret_key),
        region=cast(str, region),
    )


def load_tencent_asr_config(data_dir: Path) -> TencentAsrConfig | None:
    provider = load_tencent_asr_provider(data_dir)
    if provider is None or not (provider.secret_id and provider.secret_key and provider.region):
        return None
    return provider


def save_tencent_asr_provider(
    data_dir: Path,
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    clear_secret_key: bool,
) -> TencentAsrConfig:
    current = load_tencent_asr_provider(data_dir)
    # clear 语义为清除整对凭据（SecretId 单独残留无意义）；空字段则保留旧值。
    if clear_secret_key:
        saved_id = ""
        saved_key = ""
    else:
        saved_id = secret_id or (current.secret_id if current else "")
        saved_key = secret_key or (current.secret_key if current else "")
    path = data_dir / "config" / "providers.json"
    providers = _read_json(path)
    providers["tencent_asr"] = {
        "secret_id": saved_id,
        "secret_key": saved_key,
        "region": region,
    }
    _write_json(path, providers)
    return TencentAsrConfig(saved_id, saved_key, region)


def load_llm_provider(data_dir: Path) -> LlmProviderConfig | None:
    raw = _read_json(data_dir / "config" / "providers.json").get("llm")
    if not isinstance(raw, dict):
        return None
    provider = cast(dict[str, object], raw)
    base_url = provider.get("base_url")
    api_key = provider.get("api_key")
    model = provider.get("model")
    if not all(isinstance(value, str) for value in (base_url, api_key, model)):
        return None
    return LlmProviderConfig(cast(str, base_url), cast(str, api_key), cast(str, model))


def save_llm_provider(
    data_dir: Path,
    *,
    base_url: str,
    api_key: str,
    model: str,
    clear_api_key: bool,
) -> LlmProviderConfig:
    path = data_dir / "config" / "providers.json"
    providers = _read_json(path)
    current = load_llm_provider(data_dir)
    saved_key = "" if clear_api_key else api_key or (current.api_key if current else "")
    providers["llm"] = {"base_url": base_url, "api_key": saved_key, "model": model}
    _write_json(path, providers)
    return LlmProviderConfig(base_url, saved_key, model)


def load_web_search_provider(data_dir: Path) -> WebSearchProviderConfig | None:
    """按 providers.json 事实返回（允许空 key），供设置页读写使用。"""
    raw = _read_json(data_dir / "config" / "providers.json").get("web_search")
    if not isinstance(raw, dict):
        return None
    provider = cast(dict[str, object], raw)
    name = provider.get("provider")
    api_key = provider.get("api_key")
    if not isinstance(name, str) or not isinstance(api_key, str):
        return None
    return WebSearchProviderConfig(provider=name, api_key=api_key)


def load_web_search_config(data_dir: Path) -> WebSearchProviderConfig | None:
    """功能可用性口径：已配置且 key 非空、provider 在白名单内才返回。"""
    provider = load_web_search_provider(data_dir)
    if (
        provider is None
        or not provider.api_key
        or provider.provider not in WEB_SEARCH_PROVIDER_CHOICES
    ):
        return None
    return provider


def save_web_search_provider(
    data_dir: Path,
    *,
    provider: str,
    api_key: str,
    clear_api_key: bool,
) -> WebSearchProviderConfig:
    path = data_dir / "config" / "providers.json"
    providers = _read_json(path)
    current = load_web_search_provider(data_dir)
    saved_key = "" if clear_api_key else api_key or (current.api_key if current else "")
    providers["web_search"] = {"provider": provider, "api_key": saved_key}
    _write_json(path, providers)
    return WebSearchProviderConfig(provider, saved_key)


def llm_provider_fingerprint(provider: LlmProviderConfig) -> str:
    return sha256(f"{provider.base_url}\0{provider.api_key}".encode()).hexdigest()


def llm_consent(data_dir: Path) -> tuple[str | None, bool]:
    provider = load_llm_provider(data_dir)
    raw = _read_json(data_dir / "config" / "settings.json").get("llm_external_processing_consent")
    if not isinstance(raw, dict):
        return None, False
    consent = cast(dict[str, object], raw)
    granted_at = consent.get("granted_at")
    fingerprint = consent.get("provider_fingerprint")
    current = (
        provider is not None
        and bool(provider.api_key)
        and isinstance(fingerprint, str)
        and fingerprint == llm_provider_fingerprint(provider)
    )
    return (granted_at if isinstance(granted_at, str) else None), current


THEME_CHOICES = ("LIGHT", "DARK", "SYSTEM")
FONT_SCALE_CHOICES = ("S", "M", "L")
LANGUAGE_CHOICES = ("zh", "en")
CLOSE_BEHAVIOR_CHOICES = ("TRAY", "EXIT")
DEFAULT_THEME = "SYSTEM"
DEFAULT_FONT_SCALE = "M"
DEFAULT_LANGUAGE = "zh"
DEFAULT_CLOSE_BEHAVIOR = "TRAY"
DEFAULT_QUICK_NOTE_SHORTCUT = "Ctrl+Alt+N"
DEFAULT_AUTOSTART = False
DEFAULT_QUIZ_LAST_COUNT = 5

# 偏好键与其默认值的唯一对照：缺键即默认；写入值等于默认值时按键删除，
# settings.json 只保留用户的偏离项，consent 等未知键经读改写天然保留。
PREFERENCE_DEFAULTS: dict[str, object] = {
    "theme": DEFAULT_THEME,
    "font_scale": DEFAULT_FONT_SCALE,
    "language": DEFAULT_LANGUAGE,
    "timezone": None,
    "close_behavior": DEFAULT_CLOSE_BEHAVIOR,
    "quick_note_shortcut": DEFAULT_QUICK_NOTE_SHORTCUT,
    "autostart": DEFAULT_AUTOSTART,
    "quiz_last_count": DEFAULT_QUIZ_LAST_COUNT,
    "last_route": None,
}


def load_preferences(data_dir: Path) -> dict[str, object]:
    settings = _read_json(data_dir / "config" / "settings.json")
    theme = settings.get("theme")
    font_scale = settings.get("font_scale")
    language = settings.get("language")
    timezone = settings.get("timezone")
    close_behavior = settings.get("close_behavior")
    quick_note_shortcut = settings.get("quick_note_shortcut")
    autostart = settings.get("autostart")
    quiz_last_count = settings.get("quiz_last_count")
    last_route = settings.get("last_route")
    return {
        "theme": theme if theme in THEME_CHOICES else DEFAULT_THEME,
        "font_scale": font_scale if font_scale in FONT_SCALE_CHOICES else DEFAULT_FONT_SCALE,
        "language": language if language in LANGUAGE_CHOICES else DEFAULT_LANGUAGE,
        "timezone": (
            timezone if isinstance(timezone, str) and is_valid_timezone(timezone) else None
        ),
        "close_behavior": (
            close_behavior if close_behavior in CLOSE_BEHAVIOR_CHOICES else DEFAULT_CLOSE_BEHAVIOR
        ),
        "quick_note_shortcut": (
            quick_note_shortcut
            if isinstance(quick_note_shortcut, str) and is_valid_shortcut(quick_note_shortcut)
            else DEFAULT_QUICK_NOTE_SHORTCUT
        ),
        "autostart": autostart if isinstance(autostart, bool) else DEFAULT_AUTOSTART,
        "quiz_last_count": (
            quiz_last_count if quiz_last_count in QUIZ_COUNT_CHOICES else DEFAULT_QUIZ_LAST_COUNT
        ),
        # 上次界面路由只要求是字符串；路径是否存在由前端 NotFound 兜底。
        "last_route": last_route if isinstance(last_route, str) else None,
    }


def save_preferences(data_dir: Path, updates: Mapping[str, object]) -> dict[str, object]:
    if not updates:
        return load_preferences(data_dir)
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    for key, value in updates.items():
        if key in PREFERENCE_DEFAULTS and value == PREFERENCE_DEFAULTS[key]:
            settings.pop(key, None)
        else:
            settings[key] = value
    _write_json(path, settings)
    return load_preferences(data_dir)


def grant_llm_consent(data_dir: Path) -> str | None:
    provider = load_llm_provider(data_dir)
    if provider is None or not provider.api_key:
        return None
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    granted_at = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    settings["llm_external_processing_consent"] = {
        "provider_fingerprint": llm_provider_fingerprint(provider),
        "granted_at": granted_at,
    }
    _write_json(path, settings)
    return granted_at


# 长期记忆外发开关（工单 06）：默认开启；关闭=记忆保留本地、不再注入发给 LLM
# 的上下文，本地查看/编辑/删除与资料检索不受影响。默认值即关（True=开启），
# 按「settings.json 只存偏离项」惯例，写回默认值时删键。
def memory_outbound_enabled(data_dir: Path) -> bool:
    value = _read_json(data_dir / "config" / "settings.json").get("learner_memory_outbound_enabled")
    return True if not isinstance(value, bool) else value


def set_memory_outbound_enabled(data_dir: Path, enabled: bool) -> bool:
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    if enabled:
        settings.pop("learner_memory_outbound_enabled", None)
    else:
        settings["learner_memory_outbound_enabled"] = False
    _write_json(path, settings)
    return enabled


# Agent 全局默认授权档（通用 Agent 第二阶段工单 02）：默认 REQUEST_APPROVAL 不写键
# （偏离项惯例同上）。值域与执法在 agent 域（runs.schemas.AuthMode），本模块只
# 读写字符串，坏值回落默认档（安全方向）。
AGENT_DEFAULT_AUTH_MODES = frozenset({"REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"})
AGENT_DEFAULT_AUTH_MODE_KEY = "agent_default_auth_mode"


def agent_default_auth_mode(data_dir: Path) -> str:
    value = _read_json(data_dir / "config" / "settings.json").get(AGENT_DEFAULT_AUTH_MODE_KEY)
    if isinstance(value, str) and value in AGENT_DEFAULT_AUTH_MODES:
        return value
    return "REQUEST_APPROVAL"


def set_agent_default_auth_mode(data_dir: Path, mode: str) -> None:
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    if mode == "REQUEST_APPROVAL":
        settings.pop(AGENT_DEFAULT_AUTH_MODE_KEY, None)
    else:
        settings[AGENT_DEFAULT_AUTH_MODE_KEY] = mode
    _write_json(path, settings)


# Agent 时间能力的用户时区（时间能力 v1）：偏好 timezone（IANA 名，null=跟随
# 系统）优先，未设置或坏值回退系统本地。系统本地回退在 Windows 上是固定偏移的
# timezone 对象（非 ZoneInfo、无 IANA 名），展示名由消费方 timezone_label 处理；
# 学习计划铺排锚点不读偏好（流外确认链不可达 data_dir），统一走 local_today()
# 系统本地口径（agent/tools/time_utils.py），默认用户（timezone=null）两口径一致。
def resolve_user_timezone(data_dir: Path) -> tzinfo:
    timezone = _read_json(data_dir / "config" / "settings.json").get("timezone")
    if isinstance(timezone, str) and is_valid_timezone(timezone):
        return ZoneInfo(timezone)
    return datetime.now().astimezone().tzinfo
