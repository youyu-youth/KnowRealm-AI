import os
from io import BufferedRandom
from pathlib import Path

DATA_SUBDIRECTORIES = ("files", "cache", "exports", "backups", "config")


class DataDirectoryInUseError(RuntimeError):
    pass


class DataDirectoryLock:
    def __init__(self, handle: BufferedRandom) -> None:
        self._handle = handle

    @classmethod
    def acquire(cls, data_dir: Path) -> "DataDirectoryLock":
        lock_path = data_dir / ".knowrealm.lock"
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise DataDirectoryInUseError(
                "DATA_DIRECTORY_IN_USE：数据目录正在使用"
            ) from None
        return cls(handle)

    def release(self) -> None:
        if self._handle.closed:
            return
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()


def ensure_data_dir(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (resolved / name).mkdir(exist_ok=True)
    return resolved
