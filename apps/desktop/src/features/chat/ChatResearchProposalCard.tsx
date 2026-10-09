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

type ChatResearchProposalCardProps = {
  sessionId: string;
  /** 当轮展示态（历史恢复入口，规格 §15）；缺省回落到本客户端内存态（done 载荷）。 */
  memory?: ChatTurnMemory | null;
};

type Decision = "APPLIED" | "REJECTED";

function proposalDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

/** 消息流内的入库提案就地确认卡（研究会话 V1）：模型经 propose_ingest 创建的
 * 「建议保存」提案，确认走现有 RESEARCH_INGEST 应用器（真实抓取入库）、拒绝
 * 零变更；数据源为当轮展示态（live done 载荷或历史轮次载荷恢复），无提案时
 * 不渲染。 */
export function ChatResearchProposalCard({
  sessionId,
  memory,
}: ChatResearchProposalCardProps) {
  const { t } = useTranslation();
  const liveMemory = useChatUiStore((state) => state.turnMemory);
  const turnMemory = memory !== undefined ? memory : liveMemory;
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (turnMemory === null || turnMemory.sessionId !== sessionId) {
    return null;
  }
  const proposals = turnMemory.researchProposals;
  if (proposals.length === 0) {
    return null;
  }
  const pending = proposals.filter(
    (proposal) => decisions[proposal.proposalId] === undefined,
  );
  const decided = proposals.filter(
    (proposal) => decisions[proposal.proposalId] !== undefined,
  );

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
      aria-label={t("chat.researchProposal.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("chat.researchProposal.panelTitle")}
      </p>
      {decided.map((proposal) => (
        <p
          key={proposal.proposalId}
          className="text-label text-muted-foreground"
        >
          {decisions[proposal.proposalId] === "APPLIED"
            ? t("chat.researchProposal.accepted")
            : t("chat.researchProposal.rejected")}
        </p>
      ))}
      <ul className="flex flex-col gap-1.5">
        {pending.map((proposal) => (
          <li
            key={proposal.proposalId}
            className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5"
          >
            <span className="min-w-0 flex-1">
              <span className="text-label text-ink block truncate">
                {proposal.title}
              </span>
              <span className="text-label text-muted-foreground block truncate">
                {proposalDomain(proposal.url)}
              </span>
            </span>
            <button
              type="button"
              className="hover:bg-surface-raised rounded p-1"
              aria-label={t("chat.researchProposal.accept", {
                title: proposal.title,
              })}
              disabled={busyId !== null}
              onClick={() => decide(proposal.proposalId, true)}
            >
              <Check className="size-3.5" aria-hidden />
            </button>
            <button
              type="button"
              className="hover:bg-surface-raised rounded p-1"
              aria-label={t("chat.researchProposal.reject", {
                title: proposal.title,
              })}
              disabled={busyId !== null}
              onClick={() => decide(proposal.proposalId, false)}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      {error ? (
        <p role="alert" className="text-destructive text-label">
          {error}
        </p>
      ) : null}
    </section>
  );
}
