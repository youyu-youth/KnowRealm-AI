import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ArrowRight, RotateCcw, ShieldCheck, Undo2 } from "lucide-react";
import { agentKeys } from "@/features/agent/api/authMode";
import {
  operationHistoryApi,
  type AgentOperationOut,
} from "@/features/settings/api/operationHistory";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import { Button } from "@/components/ui/button";

type ChatExecutedOperationCardProps = {
  sessionId: string;
  /** 消息流持久锚点（assistant 行 executed_operation_ids 聚合，时间序）：
   * 查询命中→正常回执；查询缺席→「历史已清理」占位。 */
  anchorIds: string[];
};

/** operation.authorization 的窄化读取（JSON 列，坏值降级为空）。 */
function authorizationOf(
  operation: AgentOperationOut,
): Record<string, unknown> | null {
  const value = operation.authorization;
  return typeof value === "object" && value !== null ? value : null;
}

function fieldString(
  source: Record<string, unknown> | null,
  key: string,
): string | null {
  const value = source?.[key];
  return typeof value === "string" ? value : null;
}

/** 档位名翻译键（与设置页 / 审计区共用词汇）。 */
const authModeLabelKey = (mode: string) =>
  `settings.operationHistory.authMode.${mode}` as const;

/** 直执行回执的动作专属结果行：入口跳转（结果 id 缺失时不渲染）。 */
function ExecutedResultRow({
  action,
  result,
  t,
}: {
  action: string;
  result: Record<string, unknown> | null;
  t: ReturnType<typeof useTranslation>["t"];
}) {
  if (result === null) return null;
  if (action === "create_course" && typeof result.course_id === "string") {
    return (
      <Link
        to="/spaces/$courseId"
        params={{ courseId: result.course_id }}
        search={{ tab: "overview" }}
        className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
      >
        {t("chat.operationProposal.openCourse")}
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    );
  }
  if (
    action === "add_text_record_to_course" &&
    typeof result.record_id === "string"
  ) {
    return (
      <Link
        to="/records/$recordId"
        params={{ recordId: result.record_id }}
        className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
      >
        {t("chat.operationProposal.textRecord.openRecord")}
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    );
  }
  return null;
}

/** 消息流内的直执行回执卡（通用 Agent 第二阶段工单 02）：自动档免确认执行的
 * 操作呈现授权依据（当时档位、触发指令原文、时间），出问题可追溯（spec 用户
 * 故事 7）。事实源是服务端：详情经 agent_operations 会话查询恢复（断线 / 重启
 * 不依赖 SSE），存在性经消息行锚点判定——锚点在、查询空＝历史已清理，降级
 * 占位跨重启成立（spec 用户故事 33，工单 02 P2 修复）。 */
export function ChatExecutedOperationCard({
  sessionId,
  anchorIds,
}: ChatExecutedOperationCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  // 请求页大小按锚点数取（上限 200=后端契约），恢复链一次覆盖全部锚点；
  // 超过 200 锚点的极端长期会话由下方截断兜底处理。
  const limit = Math.min(200, Math.max(50, anchorIds.length));
  const operations = useQuery({
    queryKey: agentKeys.sessionOperations(sessionId),
    queryFn: () =>
      operationHistoryApi.listOperations({ session_id: sessionId, limit }),
    enabled: anchorIds.length > 0,
    staleTime: 0,
  });

  // 撤销与重试是 UI 显式动作＝用户授权（工单 06）：成功后失效会话操作查询，
  // 回执行随补偿 / 重试结果就地刷新。
  const undo = useMutation({
    mutationFn: (operationId: string) =>
      operationHistoryApi.undoOperation(operationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentKeys.sessionOperations(sessionId),
      });
      // 撤销 / 重试可能还原或重放共享引用（补偿动作类型不可知）：统一失效
      // 引用缓存（低频显式动作，代价仅挂载中查询一次重取）。
      void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
    },
  });
  const retry = useMutation({
    mutationFn: (operationId: string) =>
      operationHistoryApi.retryOperation(operationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: agentKeys.sessionOperations(sessionId),
      });
      void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
    },
  });

  // 查询未成功完成（首次加载 / 失败）不渲染：占位判定以查询成功为前提，
  // 避免把加载中或网络失败误报为「历史已清理」（提案卡「失败即无卡」同模式）。
  if (anchorIds.length === 0 || !operations.isSuccess) {
    return null;
  }
  const fetched = operations.data;
  // 锚点序=执行序；查询详情只渲染直执行路径（proposal_id 空），确认路径
  // 回写行由提案卡承载。
  const byId = new Map(
    fetched
      .filter((operation) => operation.proposal_id === null)
      .map((operation) => [operation.id, operation] as const),
  );
  const direct = anchorIds.flatMap((id) => {
    const operation = byId.get(id);
    return operation ? [operation] : [];
  });
  // 满页=可能截断（锚点超页大小）：缺席锚点不计占位——宁可不显示占位，
  // 不把「未取到」错报为「已清理」；命中的锚点照常渲染。
  const possiblyTruncated = fetched.length >= limit;
  const purgedCount = possiblyTruncated ? 0 : anchorIds.length - direct.length;

  if (direct.length === 0 && purgedCount === 0) {
    return null;
  }

  return (
    <section
      aria-label={t("chat.executedOperation.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("chat.executedOperation.panelTitle")}
      </p>
      {direct.map((operation) => {
        const authorization = authorizationOf(operation);
        const succeeded = operation.status === "SUCCEEDED";
        const undone = operation.undone_by !== null;
        // 撤销按钮状态（工单 06）：成功且可撤销且未被撤销；不可撤销时不渲染
        // 按钮（原因就地呈现，spec 用户故事 28），已撤销显示标记；补偿行
        // （undo_of 非空）仍可再撤销（恢复到撤销前）。
        const undoableRow = succeeded && operation.undoable && !undone;
        // 重试按钮状态：直执行失败项（提案路径失败走提案卡重试）。
        const retryableRow =
          operation.status === "FAILED" && operation.proposal_id === null;
        // 授权档缺失（坏 JSON）时按后端默认档口径回显，不渲染空键名。
        const authModeValue =
          fieldString(authorization, "auth_mode") ?? "REQUEST_APPROVAL";
        return (
          <div
            key={operation.id}
            className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5"
          >
            <p className="text-label text-ink flex items-center gap-1.5 font-medium">
              <ShieldCheck
                className="text-ink-muted size-3.5"
                aria-hidden="true"
              />
              {t(
                `chat.executedOperation.action.${operation.action}`,
                operation.action,
              )}
              {operation.undo_of ? (
                <span className="text-label text-muted-foreground">
                  {t("chat.executedOperation.undoBadge")}
                </span>
              ) : null}
            </p>
            <p className="text-label text-muted-foreground">
              {t("chat.executedOperation.authBasis", {
                mode: t(authModeLabelKey(authModeValue)),
              })}
            </p>
            {fieldString(authorization, "instruction_excerpt") ? (
              <p
                className="text-label text-muted-foreground"
                title={
                  fieldString(authorization, "instruction_excerpt") ?? undefined
                }
              >
                {t("chat.executedOperation.instruction", {
                  excerpt: fieldString(authorization, "instruction_excerpt"),
                })}
              </p>
            ) : null}
            <p className="text-label text-muted-foreground">
              {succeeded
                ? t("chat.executedOperation.finishedAt", {
                    time: new Date(
                      operation.finished_at ?? operation.created_at,
                    ).toLocaleString(),
                  })
                : t("chat.executedOperation.failed", {
                    reason: operation.error_code
                      ? t(
                          `errors.${operation.error_code}`,
                          operation.error_code,
                        )
                      : t("chat.executedOperation.failedUnknown"),
                  })}
            </p>
            {succeeded ? (
              <ExecutedResultRow
                action={operation.action}
                result={operation.result ?? null}
                t={t}
              />
            ) : null}
            {undone ? (
              <p className="text-label text-muted-foreground">
                {t("chat.executedOperation.undone")}
              </p>
            ) : null}
            {succeeded && !operation.undoable && operation.undo_reason ? (
              // 不可撤销原因如实呈现（spec 用户故事 28）：不只隐藏按钮，
              // 让用户知道为什么这项操作没有撤销入口。
              <p className="text-label text-muted-foreground">
                {t("chat.executedOperation.notUndoable", {
                  reason: operation.undo_reason,
                })}
              </p>
            ) : null}
            {undoableRow || retryableRow ? (
              <div className="flex items-center gap-2">
                {undoableRow ? (
                  <Button
                    size="xs"
                    variant="ghost"
                    disabled={undo.isPending}
                    onClick={() => undo.mutate(operation.id)}
                  >
                    <Undo2 data-icon="inline-start" aria-hidden="true" />
                    {t("chat.executedOperation.undo")}
                  </Button>
                ) : null}
                {retryableRow ? (
                  <Button
                    size="xs"
                    variant="ghost"
                    disabled={retry.isPending}
                    onClick={() => retry.mutate(operation.id)}
                  >
                    <RotateCcw data-icon="inline-start" aria-hidden="true" />
                    {t("chat.executedOperation.retry")}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {undo.isError && undo.variables === operation.id ? (
              <p role="alert" className="text-destructive text-label">
                {undo.error.message}
              </p>
            ) : null}
          </div>
        );
      })}
      {purgedCount > 0 ? (
        <p className="text-label text-muted-foreground">
          {t("chat.executedOperation.historyPurged", { count: purgedCount })}
        </p>
      ) : null}
    </section>
  );
}
