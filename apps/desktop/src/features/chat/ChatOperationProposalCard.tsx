import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { useChatUiStore } from "@/features/chat/chatUiStore";

type ChatOperationProposalCardProps = {
  sessionId: string;
};

type Decision = "APPLIED" | "REJECTED";

type OperationProposalView = {
  proposalId: string;
  payload: Record<string, unknown>;
};

/** 提案 payload → 确认卡字段行（标签复用新建课程表单文案，枚举值走既有翻译）。 */
function previewRows(
  payload: Record<string, unknown>,
  t: (key: string) => string,
): { label: string; value: string }[] {
  const str = (key: string) =>
    typeof payload[key] === "string" ? (payload[key] as string) : null;
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null) => {
    if (value) rows.push({ label, value });
  };
  push(t("spaces.form.name"), str("name"));
  const context = str("learning_context");
  push(
    t("spaces.form.learningContext"),
    context ? t(`spaces.learningContext.${context}`) : null,
  );
  const stage = str("education_stage");
  push(
    t("spaces.form.educationStage"),
    stage ? t(`spaces.educationStage.${stage}`) : null,
  );
  const depth = str("depth");
  push(t("spaces.form.depth"), depth ? t(`spaces.depth.${depth}`) : null);
  const courseType = str("course_type");
  push(
    t("spaces.form.courseType"),
    courseType ? t(`spaces.courseType.${courseType}`) : null,
  );
  push(t("spaces.form.courseDescription"), str("description"));
  return rows;
}

/** 消息流内的课程创建提案就地确认卡（通用 Agent 第一阶段工单 02）：
 * 模型经 create_course 创建的 COURSE_CREATE 提案，完整参数预览后确认（真实
 * 创建课程）或拒绝（零业务事实）；APPLIED 后转回执态、提供课程入口跳转。
 * 断线/重启后经既有提案查询恢复本会话的待确认提案（提案本体跨重启持久）。 */
export function ChatOperationProposalCard({
  sessionId,
}: ChatOperationProposalCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const turnMemory = useChatUiStore((state) => state.turnMemory);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [appliedCourseIds, setAppliedCourseIds] = useState<
    Record<string, string | null>
  >({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 断线/重启恢复（工单 02）：本会话 PENDING 的 COURSE_CREATE 提案。
  // queryFn 拉全局 PENDING 提案、组件内按 session 过滤（提案列表端点无会话参数）。
  const { data: pendingProposals } = useQuery({
    queryKey: libraryKeys.proposals("PENDING"),
    queryFn: () => libraryApi.listProposals({ status: "PENDING" }),
  });

  const proposals = useMemo(() => {
    const byId = new Map<string, OperationProposalView>();
    const restored = (pendingProposals ?? []).filter(
      (proposal: AgentProposalOut) =>
        proposal.proposal_type === "COURSE_CREATE" &&
        proposal.session_id === sessionId,
    );
    for (const proposal of restored) {
      byId.set(proposal.id, {
        proposalId: proposal.id,
        payload: proposal.payload ?? {},
      });
    }
    const turn =
      turnMemory?.sessionId === sessionId ? turnMemory.operationProposals : [];
    for (const proposal of turn) {
      if (!byId.has(proposal.proposalId)) {
        byId.set(proposal.proposalId, {
          proposalId: proposal.proposalId,
          payload: proposal.payload,
        });
      }
    }
    return [...byId.values()];
  }, [pendingProposals, sessionId, turnMemory]);

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
        if (result.status === "APPLIED") {
          const courseId =
            typeof result.result?.course_id === "string"
              ? result.result.course_id
              : null;
          setAppliedCourseIds((current) => ({
            ...current,
            [proposalId]: courseId,
          }));
        }
        setDecisions((current) => ({
          ...current,
          [proposalId]: result.status === "APPLIED" ? "APPLIED" : "REJECTED",
        }));
        void queryClient.invalidateQueries({
          queryKey: [...libraryKeys.all, "proposals"],
        });
      })
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setBusyId(null));
  };

  return (
    <section
      aria-label={t("chat.operationProposal.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("chat.operationProposal.panelTitle")}
      </p>
      {decided.map((proposal) => {
        const applied =
          decisions[proposal.proposalId] === "APPLIED" &&
          appliedCourseIds[proposal.proposalId] !== undefined;
        const courseId = appliedCourseIds[proposal.proposalId];
        return (
          <div
            key={proposal.proposalId}
            className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5"
          >
            <p className="text-label text-muted-foreground">
              {applied
                ? t("chat.operationProposal.accepted")
                : t("chat.operationProposal.rejected")}
            </p>
            {applied && courseId ? (
              <Link
                to="/spaces/$courseId"
                params={{ courseId }}
                search={{ tab: "overview" }}
                className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
              >
                {t("chat.operationProposal.openCourse")}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        );
      })}
      <ul className="flex flex-col gap-1.5">
        {pending.map((proposal) => {
          const rows = previewRows(proposal.payload, t);
          return (
            <li
              key={proposal.proposalId}
              className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5"
            >
              <dl className="min-w-0 flex-1">
                {rows.map((row) => (
                  <div key={row.label} className="flex gap-2">
                    <dt className="text-label text-muted-foreground shrink-0">
                      {row.label}
                    </dt>
                    <dd className="text-label text-ink min-w-0 break-words">
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.operationProposal.accept")}
                disabled={busyId !== null}
                onClick={() => decide(proposal.proposalId, true)}
              >
                <Check className="size-3.5" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="hover:bg-surface-raised rounded p-1"
                aria-label={t("chat.operationProposal.reject")}
                disabled={busyId !== null}
                onClick={() => decide(proposal.proposalId, false)}
              >
                <X className="size-3.5" aria-hidden="true" />
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
