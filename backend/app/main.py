import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

from app.agents.llm import (
    KnowledgePointModel,
    OpenAiCompatibleKnowledgePointModel,
    OpenAiCompatibleQuizModel,
    OpenAiCompatibleSummaryModel,
    QuizModel,
    SummaryModel,
)
from app.agents.summary import build_summary_graph
from app.api import (
    audio_imports,
    capture_batches,
    courses,
    document_imports,
    knowledge_points,
    processing_jobs,
    quizzes,
    recording_sessions,
    records,
    settings,
    summaries,
    today,
)
from app.api.deps import require_launch_token
from app.core.data_dir import DataDirectoryLock, ensure_data_dir
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.schemas.course import ErrorResponse
from app.services.audio_worker import AudioWorker
from app.services.cache_lifecycle_service import CacheLifecycleService
from app.services.document_cleanup_service import DocumentCleanupService
from app.services.document_worker import DocumentWorker
from app.services.knowledge_point_worker import KnowledgePointWorker
from app.services.quiz_worker import QuizWorker
from app.services.record_invalidation import RecordInvalidationNotifier
from app.services.summary_worker import SummaryWorker
from app.services.tencent_asr_client import TencentAsrClient

DEFAULT_CORS_ORIGINS = (
    "http://localhost:1420",
    "tauri://localhost",
    "http://tauri.localhost",
)


def create_app(
    *,
    data_dir: Path,
    launch_token: str,
    ffmpeg_path: Path | None = None,
    asr_client: TencentAsrClient | None = None,
    summary_model: SummaryModel | None = None,
    knowledge_point_model: KnowledgePointModel | None = None,
    quiz_model: QuizModel | None = None,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    record_notifier = RecordInvalidationNotifier()

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
            app.state.ffmpeg_path = ffmpeg_path.resolve() if ffmpeg_path is not None else None
            app.state.summary_model = summary_model or OpenAiCompatibleSummaryModel()
            app.state.knowledge_point_model = (
                knowledge_point_model or OpenAiCompatibleKnowledgePointModel()
            )
            app.state.quiz_model = quiz_model or OpenAiCompatibleQuizModel()

            async def cleanup_course_tombstones() -> None:
                try:
                    await DocumentCleanupService.purge_expired(
                        session_factory,
                        resolved_data_dir,
                    )
                except Exception:
                    logger.error(
                        "course_tombstone_cleanup_failed",
                        error_code="DOCUMENT_CLEANUP_FAILED",
                    )

            cleanup_task = asyncio.create_task(cleanup_course_tombstones())
            app.state.course_tombstone_cleanup_task = cleanup_task
            await cleanup_task
            await CacheLifecycleService.cleanup_orphans(session_factory, resolved_data_dir)
            document_worker = DocumentWorker(session_factory, resolved_data_dir, record_notifier)
            await document_worker.recover_interrupted()
            document_worker_task = asyncio.create_task(document_worker.run())
            app.state.document_worker_task = document_worker_task
            audio_worker = (
                AudioWorker(
                    session_factory,
                    resolved_data_dir,
                    ffmpeg_path.resolve(),
                    asr_client or TencentAsrClient(),
                    record_notifier,
                )
                if ffmpeg_path is not None
                else None
            )
            audio_worker_task = None
            if audio_worker is not None:
                await audio_worker.recover_interrupted()
                audio_worker_task = asyncio.create_task(audio_worker.run())
                app.state.audio_worker_task = audio_worker_task
            checkpoint_path = resolved_data_dir / "langgraph.db"
            initialize_checkpointer = not checkpoint_path.exists()
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                if initialize_checkpointer:
                    await checkpointer.setup()
                summary_graph = build_summary_graph(checkpointer)
                app.state.summary_graph = summary_graph
                summary_worker = SummaryWorker(
                    session_factory,
                    resolved_data_dir,
                    summary_graph,
                    app.state.summary_model,
                    record_notifier,
                )
                await summary_worker.recover_interrupted()
                summary_worker_task = asyncio.create_task(summary_worker.run())
                app.state.summary_worker_task = summary_worker_task
                knowledge_point_worker = KnowledgePointWorker(
                    session_factory,
                    resolved_data_dir,
                    app.state.knowledge_point_model,
                    record_notifier,
                )
                await knowledge_point_worker.recover_interrupted()
                knowledge_point_worker_task = asyncio.create_task(knowledge_point_worker.run())
                app.state.knowledge_point_worker_task = knowledge_point_worker_task
                quiz_worker = QuizWorker(
                    session_factory,
                    resolved_data_dir,
                    app.state.quiz_model,
                    record_notifier,
                )
                await quiz_worker.recover_interrupted()
                quiz_worker_task = asyncio.create_task(quiz_worker.run())
                app.state.quiz_worker_task = quiz_worker_task
                try:
                    yield
                finally:
                    quiz_worker.stop()
                    knowledge_point_worker.stop()
                    summary_worker.stop()
                    if audio_worker is not None:
                        audio_worker.stop()
                    document_worker.stop()
                    try:
                        await quiz_worker_task
                    finally:
                        try:
                            await summary_worker_task
                        finally:
                            try:
                                await knowledge_point_worker_task
                            finally:
                                try:
                                    if audio_worker_task is not None:
                                        await audio_worker_task
                                finally:
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
    app.state.record_notifier = record_notifier
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-KnowRealm-Token"],
    )
    app.include_router(courses.router)
    app.include_router(audio_imports.router)
    app.include_router(capture_batches.router)
    app.include_router(settings.router)
    app.include_router(summaries.router)
    app.include_router(knowledge_points.router)
    app.include_router(quizzes.router)
    app.include_router(today.router)
    app.include_router(document_imports.router)
    app.include_router(processing_jobs.router)
    app.include_router(recording_sessions.router)
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
        logger.error(
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
