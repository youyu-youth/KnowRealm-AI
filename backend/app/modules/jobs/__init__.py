"""任务队列平台模块：processing_jobs 表、JobRunner 执行骨架（ADR-0012）与控制面 API。

对外公开行为面：runner 协议类型、ProcessingJobService、生命周期取消与重试策略。
ORM 与 Pydantic 契约经 ``jobs.models`` / ``jobs.schemas`` 叶子直引。
"""

from app.modules.jobs.lifecycle import cancel_nonterminal_jobs
from app.modules.jobs.policy import RETRYABLE_PROCESSING_JOB_ERROR_CODES
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    JobRunner,
    LoopFailure,
    ManagedWorker,
    Ready,
    RunnerContext,
    WaitingClaim,
    WorkerSpec,
    mark_failed,
    mark_retry_backoff,
    mark_retry_fixed,
    recover_running_to_failed,
)
from app.modules.jobs.service import ProcessingJobService

__all__ = [
    "CancelClaim",
    "ClaimCheck",
    "ClaimedJob",
    "JobRunner",
    "LoopFailure",
    "ManagedWorker",
    "ProcessingJobService",
    "recover_running_to_failed",
    "Ready",
    "RETRYABLE_PROCESSING_JOB_ERROR_CODES",
    "RunnerContext",
    "WaitingClaim",
    "WorkerSpec",
    "cancel_nonterminal_jobs",
    "mark_failed",
    "mark_retry_backoff",
    "mark_retry_fixed",
]
