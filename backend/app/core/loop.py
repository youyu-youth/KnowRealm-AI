import asyncio
import selectors
import sys
from typing import Any


def _silence_proactor_disconnect_noise(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    """Windows Proactor 已知噪音（CPython gh-83594）：客户端已重置连接后
    _call_connection_lost 回调里 sock.shutdown 抛 ConnectionResetError
    (WinError 10054)，不影响功能。仅静音该形态，其余仍走默认处理器。"""
    exception = context.get("exception")
    if isinstance(exception, ConnectionResetError):
        handle = context.get("handle")
        callback = getattr(handle, "_callback", None) if handle is not None else None
        if "_call_connection_lost" in str(getattr(callback, "__qualname__", "")):
            return
    loop.default_exception_handler(context)


def sidecar_loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        loop.set_exception_handler(_silence_proactor_disconnect_noise)
        return loop
    return asyncio.SelectorEventLoop(selectors.SelectSelector())
