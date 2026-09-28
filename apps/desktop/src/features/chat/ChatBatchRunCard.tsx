import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { AgentRunProgress } from "@/features/agent/AgentRunProgress";
import { agentKeys } from "@/features/agent/api/authMode";
import {
  isRunActive,
  operationHistoryApi,
} from "@/features/settings/api/operationHistory";

/** 会话任务面板（通用 Agent 第二阶段工单 05）：本会话的档位直执行任务。
 *
 * 只呈现「档位直接授权」的任务（proposal_id 为空）——经计划卡批准的批次在计划卡
 * 内就地呈现进度（与直执行回执卡按 proposal_id 分工的先例一致）。任务独立于聊天：
 * 关页面 / 断线 / 重启后经持久化查询恢复同一视图；终态任务保留为**批次回执**
 * （工单 05 review：过滤终态会让「已开始执行」的直执行批次在聊天里没有最终结果，
 * 只能去设置页操作历史找），活跃任务排前、回执排后；完整历史与清理入口在设置页。 */
export function ChatBatchRunCard({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: agentKeys.sessionRuns(sessionId),
    queryFn: () => operationHistoryApi.listRuns({ session_id: sessionId }),
    staleTime: 0,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((run) => isRunActive(run.status))
        ? 3000
        : false,
  });

  // 分组而非重排：组内保持接口顺序（创建时间倒序）。
  const runs = useMemo(() => {
    const direct = (data ?? []).filter((run) => run.proposal_id === null);
    const active = direct.filter((run) => isRunActive(run.status));
    return [...active, ...direct.filter((run) => !isRunActive(run.status))];
  }, [data]);

  if (runs.length === 0) {
    return null;
  }
  return (
    <section
      aria-label={t("agent.run.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("agent.run.panelTitle")}
      </p>
      {runs.map((run) => (
        <AgentRunProgress key={run.id} runId={run.id} />
      ))}
    </section>
  );
}
