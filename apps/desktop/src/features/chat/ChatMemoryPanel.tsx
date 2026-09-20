import { useState } from "react";
import { Brain, Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import type { ChatMemoryProposalPayload } from "@/features/chat/api/chatSessions";

type ChatMemoryPanelProps = {
  /** 本轮实际注入的记忆条目（null = 本轮未注入，不展示）。 */
  used: string[] | null;
  /** 模型本轮新建的待确认 MEMORY 提案。 */
  proposals: ChatMemoryProposalPayload[];
};

type Decision = "APPLIED" | "REJECTED";

/** 本轮学习者记忆（工单 06）：注入条目说明 + MEMORY 提案就地确认卡。
 * 展示状态全部为组件树内临时态（done 载荷是唯一来源），确认/拒绝走提案端点。 */
export function ChatMemoryPanel({ used, proposals }: ChatMemoryPanelProps) {
  const { t } = useTranslation();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (used === null && proposals.length === 0) return null;

  const decide = (proposal: ChatMemoryProposalPayload, accept: boolean) => {
    setBusyId(proposal.proposalId);
    setError(null);
    const request: Promise<AgentProposalOut> = accept
      ? libraryApi.confirmProposal(proposal.proposalId)
      : libraryApi.rejectProposal(proposal.proposalId);
    request
      .then((result) => {
        // confirm/reject 端点只会返回终局（APPLIED/REJECTED），FAILED 走错误路径。
        setDecisions((current) => ({
          ...current,
          [proposal.proposalId]:
            result.status === "APPLIED" ? "APPLIED" : "REJECTED",
        }));
      })
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setBusyId(null));
  };

  return (
    <section
      aria-label={t("chat.memory.panelLabel")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground flex items-center gap-1.5">
        <Brain className="size-3.5" aria-hidden="true" />
        {t("chat.memory.panelTitle")}
      </p>
      {used !== null && used.length > 0 ? (
        <p className="text-label text-muted-foreground">
          {t("chat.memory.usedPrefix")}
          {used.join(t("chat.memory.usedSeparator"))}
        </p>
      ) : null}
      {used !== null && used.length === 0 ? (
        <p className="text-label text-muted-foreground">
          {t("chat.memory.usedEmpty")}
        </p>
      ) : null}
      <ul className="flex flex-col gap-1.5">
        {proposals.map((proposal) => {
          const decision = decisions[proposal.proposalId];
          if (decision !== undefined) {
            return (
              <li
                key={proposal.proposalId}
                className="text-label text-muted-foreground"
              >
                {decision === "APPLIED"
                  ? t("chat.memory.proposalAccepted")
                  : t("chat.memory.proposalRejected")}
              </li>
            );
          }
          return (
            <li
              key={proposal.proposalId}
              className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5"
            >
              <span className="text-label text-ink min-w-0 flex-1">
                {t("chat.memory.proposalPrefix")}
                {proposal.items.join(t("chat.memory.usedSeparator"))}
              </span>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.memory.accept", {
                  items: proposal.items.join(t("chat.memory.usedSeparator")),
                })}
                disabled={busyId !== null}
                onClick={() => decide(proposal, true)}
              >
                <Check className="size-3.5" aria-hidden />
              </button>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.memory.reject", {
                  items: proposal.items.join(t("chat.memory.usedSeparator")),
                })}
                disabled={busyId !== null}
                onClick={() => decide(proposal, false)}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
      {error ? (
        <p role="alert" className="text-destructive text-label">
          {error}
        </p>
      ) : null}
    </section>
  );
}
