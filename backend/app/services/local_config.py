import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class TencentAsrConfig:
    secret_id: str
    secret_key: str
    region: str


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
