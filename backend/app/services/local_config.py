import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from app.schemas.quiz import QUIZ_COUNT_CHOICES


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
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())
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


def load_tencent_asr_config(data_dir: Path) -> TencentAsrConfig | None:
    raw = _read_json(data_dir / "config" / "providers.json").get("tencent_asr")
    if not isinstance(raw, dict):
        return None
    provider = cast(dict[str, object], raw)
    secret_id = provider.get("secret_id")
    secret_key = provider.get("secret_key")
    region = provider.get("region")
    if not all(isinstance(value, str) and value for value in (secret_id, secret_key, region)):
        return None
    return TencentAsrConfig(
        secret_id=cast(str, secret_id),
        secret_key=cast(str, secret_key),
        region=cast(str, region),
    )


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


DEFAULT_QUIZ_LAST_COUNT = 5


def load_quiz_last_count(data_dir: Path) -> int:
    value = _read_json(data_dir / "config" / "settings.json").get("quiz_last_count")
    return (
        value if isinstance(value, int) and value in QUIZ_COUNT_CHOICES else DEFAULT_QUIZ_LAST_COUNT
    )


def save_quiz_last_count(data_dir: Path, count: int) -> int:
    path = data_dir / "config" / "settings.json"
    settings = _read_json(path)
    settings["quiz_last_count"] = count
    _write_json(path, settings)
    return count


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
