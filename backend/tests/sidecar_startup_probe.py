"""仅用于第二个 sidecar 的启动诊断，不改变生产入口与超时。"""

import faulthandler
import json
import sys
from pathlib import Path
from time import perf_counter

trace_path = Path(sys.argv.pop(1))
started = perf_counter()
stages: list[dict[str, str | float]] = []


def mark(stage: str) -> None:
    stages.append({"stage": stage, "elapsed_seconds": round(perf_counter() - started, 3)})
    trace_path.write_text(json.dumps(stages), encoding="utf-8")


mark("before_app_import")
faulthandler.dump_traceback_later(8)
try:
    from app.server import main

    mark("app_imported")
    main()
finally:
    faulthandler.cancel_dump_traceback_later()
    mark("exited")
