import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { agentKeys } from "@/features/agent/api/authMode";
import {
  type AgentOperationOut,
  canRetryRunSteps,
  formatRunTime,
  isRunActive,
  isRunWaiting,
  isStepRetryable,
  operationHistoryApi,
  runStatusTone,
} from "@/features/settings/api/operationHistory";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

/** 任务（Run）进度面板（通用 Agent 第二阶段工单 05）：执行中 / 等待 / 部分完成
 * 的逐项结果 + 显式唤醒按钮（继续 / 失败项重试 / 取消）。
 *
 * 唯一事实源是服务端的 agent_runs / agent_operations：断线、切页、重启后经查询
 * 恢复同一视图（不做 SSE 追加态）；推进中按 2s 轮询刷新（CourseBrain BUILDING
 * 先例），终态停轮询。按钮全部是显式动作——「继续」只对等待态开放，「重试」
 * 只对失败 / 跳过项开放，取消不冒充撤销（已提交结果保留）。 */
export function AgentRunProgress({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const run = useQuery({
    queryKey: agentKeys.runDetail(runId),
    queryFn: () => operationHistoryApi.getRun(runId),
    refetchInterval: (query) =>
      isRunActive(query.state.data?.status) ? 2000 : false,
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: agentKeys.runs() });
  }

  const act = useMutation({
    mutationFn: (action: "resume" | "cancel") =>
      action === "resume"
        ? operationHistoryApi.resumeRun(runId)
        : operationHistoryApi.cancelRun(runId),
    onSuccess: invalidate,
  });
  const retry = useMutation({
    mutationFn: (operationId: string) =>
      operationHistoryApi.retryRunOperation(runId, operationId),
    onSuccess: invalidate,
  });

  const data = run.data;
  if (data === undefined) {
    return run.isError ? (
      <p role="alert" className="text-destructive text-label">
        {run.error.message}
      </p>
    ) : (
      <p role="status" className="text-label text-muted-foreground">
        <Spinner aria-hidden="true" /> {t("settings.operationHistory.loading")}
      </p>
    );
  }
  const operations = data.operations;
  const done = operations.filter(
    (operation) => operation.status === "SUCCEEDED",
  ).length;
  const waiting = isRunWaiting(data.status);
  const active = isRunActive(data.status);
  const busy = act.isPending || retry.isPending;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`text-label font-label ${runStatusTone(data.status)}`}>
          {t(`settings.operationHistory.runStatus.${data.status}`)}
        </span>
        <span className="text-label text-muted-foreground">
          {t("agent.run.progress", { done, total: operations.length })}
        </span>
        <span className="text-label text-muted-foreground">
          {t("chat.batchPlan.version", { version: data.plan_version })}
        </span>
        <span className="min-w-0 flex-1" />
        {waiting ? (
          <Button
            size="xs"
            variant="outline"
            disabled={busy}
            onClick={() => act.mutate("resume")}
          >
            {t("agent.run.resume")}
          </Button>
        ) : null}
        {active ? (
          <Button
            size="xs"
            variant="ghost"
            disabled={busy}
            onClick={() => act.mutate("cancel")}
          >
            {t("agent.run.cancel")}
          </Button>
        ) : null}
      </div>
      {data.waiting_reason ? (
        <p role="status" className="text-label text-muted-foreground">
          {t("agent.run.waiting", {
            reason: t(`errors.${data.waiting_reason}`, data.waiting_reason),
          })}
        </p>
      ) : null}
      {data.instruction_text ? (
        <p className="text-label text-muted-foreground min-w-0 truncate">
          {t("agent.run.instruction", { text: data.instruction_text })}
        </p>
      ) : null}
      <ul className="flex flex-col gap-1">
        {operations.map((operation) => (
          <RunStepRow
            key={operation.id}
            operation={operation}
            canRetry={canRetryRunSteps(data.status)}
            busy={busy}
            onRetry={(operationId) => retry.mutate(operationId)}
          />
        ))}
      </ul>
      {act.isError ? (
        <p role="alert" className="text-destructive text-label">
          {act.error.message}
        </p>
      ) : null}
      {retry.isError ? (
        <p role="alert" className="text-destructive text-label">
          {retry.error.message}
        </p>
      ) : null}
    </div>
  );
}

/** 单个步骤行：动作 / 目标 / 状态 / 失败原因 / 重试。目标名称取快照标题
 * （提交时固化，快照缺失则退回目标 id 缩写——不造假名）。 */
function RunStepRow({
  operation,
  canRetry,
  busy,
  onRetry,
}: {
  operation: AgentOperationOut;
  canRetry: boolean;
  busy: boolean;
  onRetry: (operationId: string) => void;
}) {
  const { t } = useTranslation();
  const snapshot = operation.snapshot ?? {};
  const title =
    typeof snapshot.title === "string" && snapshot.title.trim()
      ? snapshot.title
      : operation.target_id
        ? `#${operation.target_id.slice(0, 8)}`
        : "";
  return (
    <li className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5">
      <span className="text-label font-label text-ink shrink-0">
        {t(`settings.operationHistory.action.${operation.action}`, {
          defaultValue: operation.action,
        })}
      </span>
      <span className="text-label text-muted-foreground min-w-0 flex-1 truncate">
        {title}
      </span>
      <span
        className={`text-label font-label shrink-0 ${runStatusTone(operation.status)}`}
      >
        {t(`settings.operationHistory.operationStatus.${operation.status}`)}
      </span>
      {operation.error_code ? (
        <span className="text-destructive text-label shrink-0">
          {t(`errors.${operation.error_code}`, operation.error_code)}
        </span>
      ) : null}
      {operation.error_code === "OPERATION_SNAPSHOT_STALE" ? (
        // 旧批准的快照已失效：重试沿用旧快照仍会失效，需重新预览授权
        // （在对话里重新整理该项 → 新的计划卡确认即继续推进）。
        <span className="text-label text-muted-foreground shrink-0">
          {t("agent.run.staleHint")}
        </span>
      ) : null}
      {canRetry && isStepRetryable(operation.status) ? (
        <Button
          size="xs"
          variant="ghost"
          disabled={busy}
          onClick={() => onRetry(operation.id)}
        >
          {t("agent.run.retry")}
        </Button>
      ) : null}
      <span className="text-label text-muted-foreground shrink-0">
        {formatRunTime(operation.finished_at ?? operation.created_at)}
      </span>
    </li>
  );
}
