import { useEffect } from "react";
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
import { libraryKeys } from "@/features/library/api/keys";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

/** 任务（Run）进度面板（通用 Agent 第二阶段工单 05）：执行中 / 等待 / 部分完成
 * 的逐项结果 + 显式唤醒按钮（继续 / 失败项重试 / 取消）。
 *
 * 唯一事实源是服务端的 agent_runs / agent_operations：断线、切页、重启后经查询
 * 恢复同一视图（不做 SSE 追加态）；推进中按 2s 轮询刷新（CourseBrain BUILDING
 * 先例），终态停轮询。按钮全部是显式动作——「继续」只对等待态开放，「重试」
 * 只对失败 / 跳过项开放，取消不冒充撤销（已提交结果保留）；终态任务的「整批
 * 撤销」（工单 06）按依赖逆序补偿、补偿行就地下现在列表中。 */
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
  const undoRun = useMutation({
    mutationFn: () => operationHistoryApi.undoRun(runId),
    onSuccess: invalidate,
  });

  // Run 落终态（含挂载即终态）时失效本会话提案查询（07 review 六轮 / 十轮）：
  // 后台产出的确认卡（如 PLAN_DRAFT 末步草案卡）挂在提案查询上、该查询无
  // 轮询——挂载时提案首查与 Run 首查存在跨落库提交的竞态（提案读到旧列表、
  // Run 已返回 COMPLETED，且终态停轮询），不失效则草案卡在该会话永不出现。
  // 终态后 runDetail 停轮询、引用稳定，effect 只跑一次；失效幂等无害。
  const runActive = run.data !== undefined && isRunActive(run.data.status);
  useEffect(() => {
    const sessionId = run.data?.session_id;
    if (!runActive && sessionId != null) {
      void queryClient.invalidateQueries({
        queryKey: libraryKeys.sessionProposals(sessionId),
      });
    }
  }, [runActive, run.data, queryClient]);

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
  // 整批撤销（工单 06）：终态任务且存在可撤销的成功项（未被撤销）。
  const undoableSteps = operations.filter(
    (operation) =>
      operation.status === "SUCCEEDED" &&
      operation.undoable &&
      operation.undone_by === null,
  );

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
        {!active && undoableSteps.length > 0 ? (
          <Button
            size="xs"
            variant="outline"
            disabled={undoRun.isPending}
            onClick={() => undoRun.mutate()}
          >
            {t("agent.run.undoBatch", { count: undoableSteps.length })}
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
      {undoRun.isError ? (
        <p role="alert" className="text-destructive text-label">
          {undoRun.error.message}
        </p>
      ) : null}
    </div>
  );
}

/** 单个步骤行：动作 / 目标 / 状态 / 失败原因 / 重试 / 撤销标记。目标名称取快照标题
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
      {operation.undo_of ? (
        // 补偿行（批次撤销产生）：徽章标示，撤销后逐项呈现（工单 06）。
        <span className="text-label text-muted-foreground shrink-0">
          {t("agent.run.undoBadge")}
        </span>
      ) : null}
      {operation.undone_by ? (
        <span className="text-label text-muted-foreground shrink-0">
          {t("agent.run.undoneMark")}
        </span>
      ) : null}
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
      {operation.status === "SUCCEEDED" &&
      !operation.undoable &&
      operation.undone_by === null &&
      operation.undo_reason ? (
        // 不可撤销原因如实呈现（spec 用户故事 28）：批次撤销跳过该项时
        // 用户能从行内知道为什么。
        <p className="text-label text-muted-foreground w-full">
          {t("chat.executedOperation.notUndoable", {
            reason: operation.undo_reason,
          })}
        </p>
      ) : null}
      {canRetry &&
      operation.undo_of === null &&
      isStepRetryable(operation.status) ? (
        // 补偿行（undo_of 非空，含批次撤销的失败留痕）不参与正向重试——
        // 失败补偿的正确路径是重新发起撤销（后端同口径守卫）。
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
