import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import courses, document_imports, processing_jobs, records
from app.api.deps import require_launch_token
from app.core.data_dir import DataDirectoryLock, ensure_data_dir
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.schemas.course import ErrorResponse
from app.services.course_service import CourseService
from app.services.document_worker import DocumentWorker

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
        resolved_data_dir = data_dir.expanduser().resolve()
        resolved_data_dir.mkdir(parents=True, exist_ok=True)
        data_directory_lock = DataDirectoryLock.acquire(resolved_data_dir)
        try:
            ensure_data_dir(resolved_data_dir)
            db_path = resolved_data_dir / "knowrealm.db"
            await run_migrations(db_path)
            engine, session_factory = create_database(db_path)
            app.state.session_factory = session_factory
            app.state.data_dir = resolved_data_dir

            async def cleanup_course_tombstones() -> None:
                try:
                    await CourseService.purge_expired(session_factory)
                except Exception:
                    logger.exception("course_tombstone_cleanup_failed")

            cleanup_task = asyncio.create_task(cleanup_course_tombstones())
            app.state.course_tombstone_cleanup_task = cleanup_task
            document_worker = DocumentWorker(session_factory, resolved_data_dir)
            document_worker_task = asyncio.create_task(document_worker.run())
            app.state.document_worker_task = document_worker_task
            try:
                yield
            finally:
                document_worker.stop()
                try:
                    await document_worker_task
                finally:
                    try:
                        await cleanup_task
                    finally:
                        await engine.dispose()
        finally:
            data_directory_lock.release()

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
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-KnowRealm-Token"],
    )
    app.include_router(courses.router)
    app.include_router(document_imports.router)
    app.include_router(processing_jobs.router)
    app.include_router(records.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = "；".join(str(error["msg"]) for error in exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": detail or "请求参数无效"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = str(uuid4())
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"服务器内部错误（请求编号：{request_id}）"},
        )

    @app.get(
        "/api/health",
        dependencies=[Depends(require_launch_token)],
        response_model=dict[str, str],
        responses={
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return app
