import { useState } from "react";
import { Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import {
  useChatUiStore,
  type ChatTurnMemory,
} from "@/features/chat/chatUiStore";

type ChatMemoryProposalCardProps = {
  sessionId: string;
  /** 当轮展示态（历史恢复入口，规格 §15）；缺省回落到本客户端内存态（done 载荷）。 */
  memory?: ChatTurnMemory | null;
};

type Decision = "APPLIED" | "REJECTED";

/** 消息流内的 MEMORY 提案就地确认卡（工单 06，ADR-0025）：模型经
 * propose_memory 创建的待确认提案，确认写入 / 拒绝零变更；数据源为当轮
 * 展示态（live done 载荷或历史轮次载荷恢复），无提案时不渲染。 */
export function ChatMemoryProposalCard({
  sessionId,
  memory,
}: ChatMemoryProposalCardProps) {
  const { t } = useTranslation();
  const liveMemory = useChatUiStore((state) => state.turnMemory);
  const turnMemory = memory !== undefined ? memory : liveMemory;
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (turnMemory === null || turnMemory.sessionId !== sessionId) {
    return null;
  }
  const proposals = turnMemory.proposals.filter(
    (proposal) => decisions[proposal.proposalId] === undefined,
  );
  const decided = turnMemory.proposals.filter(
    (proposal) => decisions[proposal.proposalId] !== undefined,
  );
  if (turnMemory.proposals.length === 0) {
    return null;
  }

  const decide = (proposalId: string, accept: boolean) => {
    setBusyId(proposalId);
    setError(null);
    const request: Promise<AgentProposalOut> = accept
      ? libraryApi.confirmProposal(proposalId)
      : libraryApi.rejectProposal(proposalId);
    request
      .then((result) => {
        // confirm/reject 端点只会返回终局（APPLIED/REJECTED），FAILED 走错误路径。
        setDecisions((current) => ({
          ...current,
          [proposalId]: result.status === "APPLIED" ? "APPLIED" : "REJECTED",
        }));
      })
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setBusyId(null));
  };

  return (
    <section
      aria-label={t("chat.memory.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      {decided.map((proposal) => (
        <p
          key={proposal.proposalId}
          className="text-label text-muted-foreground"
        >
          {decisions[proposal.proposalId] === "APPLIED"
            ? t("chat.memory.proposalAccepted")
            : t("chat.memory.proposalRejected")}
        </p>
      ))}
      <ul className="flex flex-col gap-1.5">
        {proposals.map((proposal) => {
          const items = proposal.items.join(t("chat.memory.usedSeparator"));
          return (
            <li
              key={proposal.proposalId}
              className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5"
            >
              <span className="text-label text-ink min-w-0 flex-1">
                {t("chat.memory.proposalPrefix")}
                {items}
              </span>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.memory.accept", { items })}
                disabled={busyId !== null}
                onClick={() => decide(proposal.proposalId, true)}
              >
                <Check className="size-3.5" aria-hidden />
              </button>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.memory.reject", { items })}
                disabled={busyId !== null}
                onClick={() => decide(proposal.proposalId, false)}
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
