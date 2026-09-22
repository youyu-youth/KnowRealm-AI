import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { agentKeys } from "@/features/agent/api/authMode";
import {
  operationHistoryApi,
  type AgentOperationOut,
} from "@/features/settings/api/operationHistory";
import { useChatUiStore } from "@/features/chat/chatUiStore";

type ChatExecutedOperationCardProps = {
  sessionId: string;
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
 * 故事 7）。事实源是服务端 agent_operations（按会话过滤）：断线 / 重启经查询
 * 恢复；本轮 done 载荷中的 operation_id 在查询缺席时降级「历史已清理」占位
 * （显式清理不静默吞掉消息流痕迹）。 */
export function ChatExecutedOperationCard({
  sessionId,
}: ChatExecutedOperationCardProps) {
  const { t } = useTranslation();
  // 本会话直执行 operations（proposal_id 空＝直执行路径；确认路径回写的
  // operation 由提案卡承载）。staleTime 0 + key 含会话：刷新即拉最新。
  const operations = useQuery({
    queryKey: agentKeys.sessionOperations(sessionId),
    queryFn: () =>
      operationHistoryApi.listOperations({ session_id: sessionId }),
    staleTime: 0,
  });
  // 当轮 done 载荷（内存态）：仅在「查询缺席但本轮确有执行」时补占位。
  const turnExecuted = useChatUiStore((state) => state.turnExecuted);

  const direct = (operations.data ?? []).filter(
    (operation) => operation.proposal_id === null,
  );
  const knownIds = new Set(direct.map((operation) => operation.id));
  const purgedCount =
    turnExecuted?.sessionId === sessionId
      ? turnExecuted.operations.filter(
          (entry) => !knownIds.has(entry.operationId),
        ).length
      : 0;

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
