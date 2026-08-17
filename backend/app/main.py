from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import courses
from app.api.deps import require_launch_token
from app.core.data_dir import ensure_data_dir
from app.db.engine import create_database
from app.db.migrations import run_migrations

DEFAULT_CORS_ORIGINS = (
    "http://localhost:1420",
    "tauri://localhost",
    "http://tauri.localhost",
)


def create_app(
    *,
    data_dir: Path,
    launch_token: str,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        resolved_data_dir = ensure_data_dir(data_dir)
        db_path = resolved_data_dir / "knowrealm.db"
        await run_migrations(db_path)
        engine, session_factory = create_database(db_path)
        app.state.session_factory = session_factory
        yield
        await engine.dispose()

    app = FastAPI(
        title="KnowRealm API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.launch_token = launch_token
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-KnowRealm-Token"],
    )
    app.include_router(courses.router)

    @app.get(
        "/api/health",
        dependencies=[Depends(require_launch_token)],
        response_model=dict[str, str],
    )
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return app
