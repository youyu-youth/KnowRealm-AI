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
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.data_dir import (
    DataDirectoryLock,
    bind_data_dir,
    ensure_data_dir,
    unbind_data_dir,
)
from app.core.version import APP_VERSION
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent import chat_sessions
from app.modules.agent.auth_mode import router as agent_auth_mode_router
from app.modules.agent.context_budget.routes import router as chat_context_router
from app.modules.agent.operations.plan_draft import plan_draft_spec
from app.modules.agent.response_process import recover_processes
from app.modules.agent.runs import routes as agent_runs_routes
from app.modules.agent.runs.worker import agent_run_spec
from app.modules.agent.turns.routes import router as chat_turns_router
from app.modules.agent.turns.runtime import (
    ActiveTurnRegistry,
    ChatTurnRecovery,
    TurnEventBroadcaster,
)
from app.modules.agent.turns.worker import chat_turn_spec
from app.modules.capture import (
    audio_imports,
    capture_batches,
    document_imports,
    recording_sessions,
    text_captures,
)
from app.modules.capture.web_fetch_worker import web_fetch_spec
from app.modules.course import courses
from app.modules.course.tombstone_cleanup import DocumentCleanupService
from app.modules.course_brain import routes as course_brain_routes
from app.modules.course_brain.worker import course_brain_spec
from app.modules.data import routes as data_routes
from app.modules.data.archive import (
    create_rolling_backup,
    ensure_pre_upgrade_snapshot,
    restore_archive,
)
from app.modules.jobs import processing_jobs
from app.modules.jobs.runner import JobRunner, ManagedWorker
from app.modules.knowledge_point import knowledge_points
from app.modules.knowledge_point.worker import knowledge_point_spec
from app.modules.learner import routes as learner_routes
from app.modules.learning import routes as learning_routes
from app.modules.learning.consumer import EvidenceConsumer
from app.modules.learning.service import MasteryService
from app.modules.learning_plan import practice_routes
from app.modules.learning_plan import study_routes
from app.modules.learning_plan import routes as learning_plan_routes
from app.modules.learning_plan.practice_worker import practice_spec
from app.modules.library import routes as library_routes
from app.modules.library import shared_refs_routes
from app.modules.library.backfill import backfill_spec, ensure_backfill_enqueued
from app.modules.library.index_rebuild_worker import index_rebuild_spec
from app.modules.library.lifecycle import LibraryLifecycleService
from app.modules.llm.service import (
    CourseBrainModel,
    KnowledgePointModel,
    OpenAiCompatibleCourseBrainModel,
    OpenAiCompatibleKnowledgePointModel,
    OpenAiCompatibleOrganizeModel,
    OpenAiCompatibleQuizGradingModel,
    OpenAiCompatibleQuizModel,
    OpenAiCompatibleReviewMaterialModel,
    OpenAiCompatibleSummaryModel,
    OpenAiCompatibleTodoModel,
    QuizGradingModel,
    QuizModel,
    ReviewMaterialModel,
    StructuredModel,
    SummaryModel,
    TodoModel,
)
from app.modules.profile import profile
from app.modules.quiz import quiz_tests, quizzes
from app.modules.quiz.grading_worker import quiz_grading_spec
from app.modules.quiz.worker import quiz_spec
from app.modules.record import records
from app.modules.review_material import review_materials
from app.modules.review_material.graph import build_review_material_graph
from app.modules.review_material.worker import review_material_spec
from app.modules.search import search as search_routes
from app.modules.search.segment_service import SegmentSearchService
from app.modules.search.service import SearchService
from app.modules.search.tokenizer import warmup as warmup_jieba
from app.modules.settings import routes as settings_routes
from app.modules.source_anchor import source_anchors
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
from app.modules.transcript.segments import SegmentService
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
    review_material_model: ReviewMaterialModel | None = None,
    course_brain_model: CourseBrainModel | None = None,
    organize_model: StructuredModel | None = None,
    import_archive: Path | None = None,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    record_notifier = RecordInvalidationNotifier()
    # ChatTurn 运行时协作件（票 01）：事件通知降延迟 + 在途执行登记 + 启动对账闸门。
    turn_broadcaster = TurnEventBroadcaster()
    turn_active_registry = ActiveTurnRegistry()
    turn_recovery = ChatTurnRecovery()

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
            # 升级前快照：旧库应用新 Schema 前先落独立保护副本；失败停止启动保留旧数据。
            await ensure_pre_upgrade_snapshot(db_path, resolved_data_dir / "backups")
            await run_migrations(db_path)
            try:
                await create_rolling_backup(db_path, resolved_data_dir / "backups")
            except Exception:
                logger.error("rolling_backup_failed", error_code="ROLLING_BACKUP_FAILED")
            engine, session_factory = create_database(db_path)
            app.state.session_factory = session_factory
            await recover_processes(session_factory)
            app.state.data_dir = resolved_data_dir
            # 进程级绑定（工单 03）：提案应用器读 provider 配置用（app.state 不可达处）。
            bind_data_dir(resolved_data_dir)
            # 资料库回填任务入队（幂等：已有活动任务则跳过）；失败不阻断启动，
            # capture 流程的同事务入队钩子会兜底。
            try:
                async with session_factory() as session, session.begin():
                    if await ensure_backfill_enqueued(session):
                        logger.info("library_backfill_enqueued")
            except Exception:
                logger.error(
                    "library_backfill_enqueue_failed",
                    error_code="LIBRARY_BACKFILL_ENQUEUE_FAILED",
                )
            # 索引是可再生衍生数据：回填失败不阻断启动，下次启动重试（与滚动备份同容错级）。
            try:
                # jieba 词典首载约 0.5~1s，放线程池预热避免阻塞事件循环（ADR-0016）。
                await asyncio.to_thread(warmup_jieba)
                await SearchService.backfill_missing(session_factory)
            except Exception:
                logger.error("search_index_backfill_failed", error_code="SEARCH_BACKFILL_FAILED")
            # 分片同为可再生派生数据：回填失败不阻断启动，下次启动重试（同容错级）。
            try:
                await SegmentService.backfill_missing(session_factory)
            except Exception:
                logger.error(
                    "transcript_segments_backfill_failed", error_code="SEGMENT_BACKFILL_FAILED"
                )
            # 分片检索索引同为可再生衍生数据：回填失败不阻断启动，下次启动重试。
            try:
                await SegmentSearchService.backfill_missing(session_factory)
            except Exception:
                logger.error(
                    "segment_search_index_backfill_failed",
                    error_code="SEGMENT_SEARCH_BACKFILL_FAILED",
                )
            # Mastery 快照同为可再生派生数据：缺失/算法版本过期/stale 标记的概念全量重建，
            # 失败不阻断启动，下次启动重试（幂等，版本一致的快照零写入）。
            recovery_failed: set[str] = set()
            try:
                recovery_failed = await MasteryService.recover_snapshots(session_factory)
            except Exception as exc:
                logger.error(
                    "mastery_snapshot_recover_failed",
                    error_code="MASTERY_RECOVER_FAILED",
                    error=repr(exc),
                )
            app.state.ffmpeg_path = ffmpeg_path.resolve() if ffmpeg_path is not None else None
            app.state.summary_model = summary_model or OpenAiCompatibleSummaryModel()
            app.state.knowledge_point_model = (
                knowledge_point_model or OpenAiCompatibleKnowledgePointModel()
            )
            app.state.quiz_model = quiz_model or OpenAiCompatibleQuizModel()
            app.state.quiz_grading_model = quiz_grading_model or OpenAiCompatibleQuizGradingModel()
            app.state.todo_model = todo_model or OpenAiCompatibleTodoModel()
            app.state.review_material_model = (
                review_material_model or OpenAiCompatibleReviewMaterialModel()
            )
            app.state.course_brain_model = course_brain_model or OpenAiCompatibleCourseBrainModel()
            app.state.organize_model = organize_model or OpenAiCompatibleOrganizeModel()
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
            # 资料条目回收站保留期清理（05）：30 天届满且无活动引用才物理删除，
            # 失败仅记日志（与索引回填同容错级，下次启动重试）。
            try:
                await LibraryLifecycleService.purge_expired_trash(session_factory)
            except Exception:
                logger.error(
                    "library_trash_cleanup_failed",
                    error_code="LIBRARY_TRASH_CLEANUP_FAILED",
                )
            await CacheLifecycleService.cleanup_orphans(session_factory, resolved_data_dir)
            checkpoint_path = resolved_data_dir / "langgraph.db"
            initialize_checkpointer = not checkpoint_path.exists()
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                if initialize_checkpointer:
                    await checkpointer.setup()
                summary_graph = build_summary_graph(checkpointer)
                review_material_graph = build_review_material_graph(checkpointer)
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
                        "review_material",
                        lambda: JobRunner(
                            review_material_spec(
                                session_factory,
                                resolved_data_dir,
                                review_material_graph,
                                app.state.review_material_model,
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
                    (
                        "course_brain",
                        lambda: JobRunner(
                            course_brain_spec(
                                session_factory,
                                resolved_data_dir,
                                app.state.course_brain_model,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "library_backfill",
                        lambda: JobRunner(
                            backfill_spec(session_factory, record_notifier),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "web_fetch",
                        lambda: JobRunner(
                            web_fetch_spec(
                                session_factory,
                                resolved_data_dir,
                                record_notifier,
                            ),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "library_index_rebuild",
                        lambda: JobRunner(
                            index_rebuild_spec(session_factory, record_notifier),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    # Run 推进（工单 05）：AGENT_RUN 触发 job 是无状态触发器，
                    # Run 状态是唯一事实源（不引入第二套调度器）。
                    (
                        "agent_run",
                        lambda: JobRunner(
                            agent_run_spec(session_factory, record_notifier),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    # 计划草案生成（工单 07）：多资料 Run 末步提交的 PLAN_DRAFT
                    # job——LLM 生成不占推进事务，完成时落草案确认卡。
                    (
                        "plan_draft",
                        lambda: JobRunner(
                            plan_draft_spec(session_factory, record_notifier, resolved_data_dir),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    (
                        "practice_prepare",
                        lambda: JobRunner(
                            practice_spec(session_factory, resolved_data_dir),
                            session_factory,
                            record_notifier,
                        ),
                    ),
                    # ChatTurn 双执行槽（票 01）：会话 A/B 独立推进，数据库条件领取
                    # 防双领取；轮次状态以 chat_turns 为唯一事实源。
                    *[
                        (
                            f"chat_turn_{slot}",
                            lambda: JobRunner(
                                chat_turn_spec(
                                    session_factory=session_factory,
                                    data_dir=resolved_data_dir,
                                    checkpointer=checkpointer,
                                    broadcaster=turn_broadcaster,
                                    active=turn_active_registry,
                                    notifier=record_notifier,
                                    recovery=turn_recovery,
                                ),
                                session_factory,
                                record_notifier,
                            ),
                        )
                        for slot in range(2)
                    ],
                ]
                if ffmpeg_path is not None:
                    worker_factories.insert(1, ("audio", audio_factory))

                workers = [(name, factory()) for name, factory in worker_factories]
                worker_tasks: list[asyncio.Task[None]] = []
                for _name, worker in workers:
                    await worker.recover_interrupted()
                    worker_tasks.append(asyncio.create_task(worker.run()))
                app.state.worker_tasks = worker_tasks
                # 学习事件消费循环（ADR-0021）：不入 processing_jobs 的独立水位循环，
                # 水位仅存内存、重启全量补扫靠 event_id 唯一约束去重。
                evidence_consumer = EvidenceConsumer(session_factory)
                consumer_task = asyncio.create_task(evidence_consumer.run())
                app.state.evidence_consumer = evidence_consumer
                # 启动恢复的残留失败交 consumer 在轮询内继续重试（快照已标 stale 兜底）。
                if recovery_failed:
                    logger.error(
                        "mastery_recover_pending_retry",
                        error_code="MASTERY_RECOVER_PENDING_RETRY",
                        concept_count=len(recovery_failed),
                    )
                    evidence_consumer.schedule_recompute(recovery_failed)
                try:
                    yield
                finally:
                    # 逆序停止并等待（与启动相反）；engine.dispose 为唯一收尾 finally
                    evidence_consumer.stop()
                    await consumer_task
                    for _name, worker in reversed(workers):
                        worker.stop()
                    for task in reversed(worker_tasks):
                        await task
                    await cleanup_task
                    await engine.dispose()
        finally:
            unbind_data_dir()
            data_directory_lock.release()

    app = FastAPI(
        title="KnowRealm API",
        version=APP_VERSION,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.launch_token = launch_token
    app.state.record_notifier = record_notifier
    app.state.turn_broadcaster = turn_broadcaster
    app.state.turn_active_registry = turn_active_registry
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-KnowRealm-Token"],
    )
    app.include_router(courses.router)
    app.include_router(course_brain_routes.router)
    app.include_router(learning_routes.router)
    app.include_router(learning_plan_routes.router)
    app.include_router(practice_routes.router)
    app.include_router(study_routes.router)
    app.include_router(audio_imports.router)
    app.include_router(capture_batches.router)
    app.include_router(settings_routes.router)
    app.include_router(data_routes.router)
    app.include_router(summaries.router)
    app.include_router(review_materials.router)
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
    app.include_router(library_routes.library_router)
    app.include_router(library_routes.proposals_router)
    app.include_router(shared_refs_routes.router)
    app.include_router(learner_routes.learner_router)
    app.include_router(search_routes.router)
    app.include_router(source_anchors.router)
    app.include_router(chat_sessions.router)
    app.include_router(chat_turns_router)
    app.include_router(chat_context_router)
    app.include_router(agent_auth_mode_router)
    app.include_router(agent_runs_routes.router)
    app.include_router(profile.router)

    # 统一 HTTP 错误序列化：{detail, code, params?}（CodedHTTPException 携带码；
    # 框架级 404/405 等裸星形异常回退 HTTP_ERROR，见 ADR-0017）。
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        content: dict[str, object] = {
            "detail": exc.detail,
            "code": getattr(exc, "code", None) or "HTTP_ERROR",
        }
        params = getattr(exc, "params", None)
        if params:
            content["params"] = params
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(  # pyright: ignore[reportUnusedFunction]
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = "；".join(str(error["msg"]) for error in exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "detail": detail or "请求参数无效",
                "code": "REQUEST_VALIDATION_FAILED",
            },
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
            content={
                "detail": f"服务器内部错误（请求编号：{request_id}）",
                "code": "INTERNAL_ERROR",
                "params": {"request_id": request_id},
            },
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
