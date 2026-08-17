from pathlib import Path

DATA_SUBDIRECTORIES = ("files", "cache", "exports", "backups", "config")


def ensure_data_dir(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (resolved / name).mkdir(exist_ok=True)
    return resolved
