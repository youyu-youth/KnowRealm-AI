import asyncio
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

from app.core.data_dir import DataDirectoryLock, ensure_data_dir
from app.core.version import APP_VERSION
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.capture import (
    audio_imports,
    capture_batches,
    document_imports,
    recording_sessions,
    text_captures,
)
from app.modules.chat import chat_sessions
from app.modules.chat.message_service import ChatStreamRegistry
from app.modules.course import courses
from app.modules.course.tombstone_cleanup import DocumentCleanupService
from app.modules.data import routes as data_routes
from app.modules.data.archive import create_rolling_backup, restore_archive
from app.modules.jobs import processing_jobs
from app.modules.jobs.runner import JobRunner, ManagedWorker
from app.modules.knowledge_point import knowledge_points
from app.modules.knowledge_point.worker import knowledge_point_spec
from app.modules.llm.service import (
    KnowledgePointModel,
    OpenAiCompatibleKnowledgePointModel,
    OpenAiCompatibleQuizGradingModel,
    OpenAiCompatibleQuizModel,
    OpenAiCompatibleSummaryModel,
    OpenAiCompatibleTodoModel,
    QuizGradingModel,
    QuizModel,
    SummaryModel,
    TodoModel,
)
from app.modules.profile import profile
from app.modules.quiz import quiz_tests, quizzes
from app.modules.quiz.grading_worker import quiz_grading_spec
from app.modules.quiz.worker import quiz_spec
from app.modules.record import records
from app.modules.settings import routes as settings_routes
from app.modules.summary import summaries
from app.modules.summary.graph import build_summary_graph
from app.modules.summary.worker import summary_spec
from app.modules.today import today
from app.modules.todo import todos
from app.modules.todo.worker import todo_spec
from app.modules.transcript.audio_worker import audio_spec
from app.modules.transcript.cache_lifecycle import CacheLifecycleService
from app.modules.transcript.document_worker import document_spec
from app.modules.transcript.integrations.tencent import TencentAsrClient
from app.shared.deps import require_launch_token
from app.shared.events import RecordInvalidationNotifier
from app.shared.schemas import ErrorResponse

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
    quiz_grading_model: QuizGradingModel | None = None,
    todo_model: TodoModel | None = None,
    import_archive: Path | None = None,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    record_notifier = RecordInvalidationNotifier()
    chat_stream_registry = ChatStreamRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        resolved_data_dir = data_dir.expanduser().resolve()
        ensure_data_dir(resolved_data_dir)
        # 导入落位必须在目录锁与开库之前：校验拒绝时数据目录仍是原样。
        if import_archive is not None:
            await restore_archive(resolved_data_dir, import_archive)
        data_directory_lock = DataDirectoryLock.acquire(resolved_data_dir)
        try:
            db_path = resolved_data_dir / "knowrealm.db"
            await run_migrations(db_path)
            try:
                await create_rolling_backup(db_path, resolved_data_dir / "backups")
            except Exception:
                logger.error("rolling_backup_failed", error_code="ROLLING_BACKUP_FAILED")
            engine, session_factory = create_database(db_path)
            app.state.session_factory = session_factory
            app.state.data_dir = resolved_data_dir
            app.state.ffmpeg_path = ffmpeg_path.resolve() if ffmpeg_path is not None else None
            app.state.summary_model = summary_model or OpenAiCompatibleSummaryModel()
            app.state.knowledge_point_model = (
                knowledge_point_model or OpenAiCompatibleKnowledgePointModel()
            )
            app.state.quiz_model = quiz_model or OpenAiCompatibleQuizModel()
            app.state.quiz_grading_model = quiz_grading_model or OpenAiCompatibleQuizGradingModel()
            app.state.todo_model = todo_model or OpenAiCompatibleTodoModel()
            app.state.asr_client = asr_client or TencentAsrClient()

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
            checkpoint_path = resolved_data_dir / "langgraph.db"
            initialize_checkpointer = not checkpoint_path.exists()
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                if initialize_checkpointer:
                    await checkpointer.setup()
                summary_graph = build_summary_graph(checkpointer)
                app.state.summary_graph = summary_graph
                app.state.chat_checkpointer = checkpointer

                def audio_factory() -> ManagedWorker:
                    return JobRunner(
                        audio_spec(
                            session_factory,
                            resolved_data_dir,
                            cast("Path", ffmpeg_path).resolve(),
                            app.state.asr_client,
                            record_notifier,
                        ),
                        session_factory,
                        record_notifier,
                    )

                # 显式 worker 工厂表：启动顺序即表序（document → audio → LLM 五域）
                worker_factories: list[tuple[str, Callable[[], ManagedWorker]]] = [
                    (
                        "document",
                        lambda: JobRunner(
                            document_spec(session_factory, resolved_data_dir, record_notifier),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "summary",
                        lambda: JobRunner(
                            summary_spec(
                                session_factory,
                                resolved_data_dir,
                                summary_graph,
                                app.state.summary_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "knowledge_point",
                        lambda: JobRunner(
                            knowledge_point_spec(
                                session_factory,
                                resolved_data_dir,
                                app.state.knowledge_point_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "quiz",
                        lambda: JobRunner(
                            quiz_spec(
                                session_factory,
                                resolved_data_dir,
                                app.state.quiz_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "quiz_grading",
                        lambda: JobRunner(
                            quiz_grading_spec(
                                session_factory,
                                resolved_data_dir,
                                app.state.quiz_grading_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "todo",
                        lambda: JobRunner(
                            todo_spec(
                                session_factory,
                                resolved_data_dir,
                                app.state.todo_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                ]
                if ffmpeg_path is not None:
                    worker_factories.insert(1, ("audio", audio_factory))

                workers = [(name, factory()) for name, factory in worker_factories]
                worker_tasks: list[asyncio.Task[None]] = []
                for _name, worker in workers:
                    await worker.recover_interrupted()
                    worker_tasks.append(asyncio.create_task(worker.run()))
                app.state.worker_tasks = worker_tasks
                try:
                    yield
                finally:
                    # 逆序停止并等待（与启动相反）；engine.dispose 为唯一收尾 finally
                    for _name, worker in reversed(workers):
                        worker.stop()
                    for task in reversed(worker_tasks):
                        await task
                    await cleanup_task
                    await engine.dispose()
        finally:
            data_directory_lock.release()

    app = FastAPI(
        title="KnowRealm API",
        version=APP_VERSION,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.launch_token = launch_token
    app.state.record_notifier = record_notifier
    app.state.chat_stream_registry = chat_stream_registry
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
    app.include_router(settings_routes.router)
    app.include_router(data_routes.router)
    app.include_router(summaries.router)
    app.include_router(knowledge_points.router)
    app.include_router(quizzes.router)
    app.include_router(quiz_tests.router)
    app.include_router(todos.router)
    app.include_router(today.router)
    app.include_router(document_imports.router)
    app.include_router(processing_jobs.router)
    app.include_router(recording_sessions.router)
    app.include_router(records.router)
    app.include_router(text_captures.router)
    app.include_router(chat_sessions.router)
    app.include_router(profile.router)

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
