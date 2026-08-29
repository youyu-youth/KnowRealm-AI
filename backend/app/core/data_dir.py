from pathlib import Path

from filelock import FileLock, Timeout

DATA_SUBDIRECTORIES = ("files", "cache", "exports", "backups", "config")


class DataDirectoryInUseError(RuntimeError):
    pass


class DataDirectoryLock:
    """数据目录单实例占用锁；实例必须存活于整个持锁期间（FileLock 随对象回收自动释放）。"""

    def __init__(self, lock: FileLock) -> None:
        self._lock = lock

    @classmethod
    def acquire(cls, data_dir: Path) -> "DataDirectoryLock":
        # timeout=0 = 单次尝试立即失败（filelock 默认 -1 是无限等待）；
        # preserve_lock_file 保持锁文件残留，与旧实现的磁盘形态一致。
        lock = FileLock(str(data_dir / ".knowrealm.lock"), timeout=0, preserve_lock_file=True)
        try:
            lock.acquire()
        except Timeout:
            raise DataDirectoryInUseError("DATA_DIRECTORY_IN_USE：数据目录正在使用") from None
        return cls(lock)

    def release(self) -> None:
        if not self._lock.is_locked:
            return
        self._lock.release()


def ensure_data_dir(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (resolved / name).mkdir(exist_ok=True)
    return resolved
