import logging
import sys
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


def setup_logging(data_dir: Path | None = None) -> None:
    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        named = logging.getLogger(name)
        named.handlers = [handler]
        named.propagate = False
    sinks = [
        {
            "sink": sys.stderr,
            "level": "INFO",
            "backtrace": False,
            "diagnose": False,
        }
    ]
    if data_dir is not None:
        logs_dir = data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        sinks.append(
            {
                "sink": logs_dir / "backend.log",
                "level": "INFO",
                "backtrace": False,
                "diagnose": False,
                "rotation": "10 MB",
                "retention": 5,
                "encoding": "utf-8",
            }
        )
    logger.configure(handlers=sinks)
