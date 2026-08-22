import asyncio
import selectors
import sys


def sidecar_loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.SelectorEventLoop(selectors.SelectSelector())
