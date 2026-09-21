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
import { Button } from "@/components/ui/button";

type ChatOperationProposalCardProps = {
  sessionId: string;
};

type Decision = "APPLIED" | "REJECTED";

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
 * 提案本体唯一事实源是服务端（agent_proposals 表）：当轮 done 失效重取与
 * 断线/重启恢复共用同一查询缓存，前端不另存副本。 */
export function ChatOperationProposalCard({
  sessionId,
}: ChatOperationProposalCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [appliedCourseIds, setAppliedCourseIds] = useState<
    Record<string, string | null>
  >({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 本会话 PENDING 的 COURSE_CREATE 提案：queryFn 拉全局 PENDING 提案、
  // 组件内按 session 过滤（提案列表端点无会话参数）。
  const { data: pendingProposals } = useQuery({
    queryKey: libraryKeys.proposals("PENDING"),
    queryFn: () => libraryApi.listProposals({ status: "PENDING" }),
  });

  const pending = useMemo(
    () =>
      (pendingProposals ?? []).filter(
        (proposal: AgentProposalOut) =>
          proposal.proposal_type === "COURSE_CREATE" &&
          proposal.session_id === sessionId &&
          decisions[proposal.id] === undefined,
      ),
    [pendingProposals, sessionId, decisions],
  );

  // 回执只依赖本地决定结果、不依赖 PENDING 列表：确认后提案从服务端
  // PENDING 移除，回执仍在当轮保留（重启后不恢复，按服务端状态重显）。
  const decided = useMemo(
    () =>
      Object.entries(decisions).map(([proposalId, decision]) => ({
        proposalId,
        decision,
        courseId: appliedCourseIds[proposalId],
      })),
    [decisions, appliedCourseIds],
  );

  if (pending.length === 0 && decided.length === 0) {
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
      {decided.map(({ proposalId, decision, courseId }) => {
        const applied = decision === "APPLIED" && courseId !== undefined;
        return (
          <div
            key={proposalId}
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
          const rows = previewRows(proposal.payload ?? {}, t);
          return (
            <li
              key={proposal.id}
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
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("chat.operationProposal.accept")}
                disabled={busyId !== null}
                onClick={() => decide(proposal.id, true)}
              >
                <Check className="size-3.5" aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("chat.operationProposal.reject")}
                disabled={busyId !== null}
                onClick={() => decide(proposal.id, false)}
              >
                <X className="size-3.5" aria-hidden="true" />
              </Button>
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
