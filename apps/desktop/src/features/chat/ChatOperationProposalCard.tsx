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

/** 确认/拒绝成功后的即时覆盖层：免去等 refetch 的空窗闪烁；远端到位后两者一致。 */
type DecisionOverride = {
  status: "APPLIED" | "REJECTED";
  courseId: string | null;
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
 * 提案本体唯一事实源是服务端（agent_proposals 表）：断线/重启经本会话全状态
 * 提案查询恢复状态视图（工单 02 review）——APPLIED 的课程入口、FAILED 的
 * 失败原因与重试、REJECTED 的终态文案均由查询还原，不依赖组件内存。 */
export function ChatOperationProposalCard({
  sessionId,
}: ChatOperationProposalCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [overrides, setOverrides] = useState<Record<string, DecisionOverride>>(
    {},
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 本会话全状态提案（后端 session_id 过滤，工单 02 review）。
  // staleTime 0 + key 含会话：重启、切回会话、断线后重进一律挂载即拉最新。
  const { data: sessionProposals } = useQuery({
    queryKey: libraryKeys.sessionProposals(sessionId),
    queryFn: () => libraryApi.listProposals({ session_id: sessionId }),
    staleTime: 0,
  });

  const proposals = useMemo(
    () =>
      (sessionProposals ?? []).filter(
        (proposal: AgentProposalOut) =>
          proposal.proposal_type === "COURSE_CREATE" &&
          proposal.session_id === sessionId,
      ),
    [sessionProposals, sessionId],
  );

  if (proposals.length === 0) {
    return null;
  }
  const statusOf = (proposal: AgentProposalOut): AgentProposalOut["status"] =>
    overrides[proposal.id]?.status ?? proposal.status;
  const settled = proposals.filter(
    (proposal) =>
      statusOf(proposal) === "APPLIED" || statusOf(proposal) === "REJECTED",
  );
  // FAILED 保留操作按钮：后端允许对 FAILED 再确认（重试语义，工单 05）。
  const actionable = proposals.filter(
    (proposal) =>
      statusOf(proposal) === "PENDING" || statusOf(proposal) === "FAILED",
  );

  const decide = (proposalId: string, accept: boolean) => {
    setBusyId(proposalId);
    setError(null);
    const request: Promise<AgentProposalOut> = accept
      ? libraryApi.confirmProposal(proposalId)
      : libraryApi.rejectProposal(proposalId);
    request
      .then((result) => {
        setOverrides((current) => ({
          ...current,
          [proposalId]: {
            status: result.status === "APPLIED" ? "APPLIED" : "REJECTED",
            courseId:
              typeof result.result?.course_id === "string"
                ? result.result.course_id
                : null,
          },
        }));
        void queryClient.invalidateQueries({
          queryKey: [...libraryKeys.all, "proposals"],
        });
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : String(exc));
        // 确认超时/失败后回查真相（工单 02 review）：请求可能已实际应用
        // （回执经查询还原），或已落 FAILED（失败原因 + 可重试）。
        void queryClient.invalidateQueries({
          queryKey: libraryKeys.sessionProposals(sessionId),
        });
      })
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
      {settled.map((proposal) => {
        const applied = statusOf(proposal) === "APPLIED";
        const override = overrides[proposal.id];
        const courseId = override
          ? (override.courseId ?? courseIdOf(proposal))
          : courseIdOf(proposal);
        return (
          <div
            key={proposal.id}
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
        {actionable.map((proposal) => {
          const rows = previewRows(proposal.payload ?? {}, t);
          return (
            <li
              key={proposal.id}
              className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5"
            >
              {statusOf(proposal) === "FAILED" ? (
                <p role="alert" className="text-destructive text-label w-full">
                  {proposal.error_code
                    ? t("chat.operationProposal.failedDetail", {
                        reason: t(
                          `errors.${proposal.error_code}`,
                          proposal.error_code,
                        ),
                      })
                    : t("chat.operationProposal.failed")}
                </p>
              ) : null}
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

/** 回执课程 id：读提案 result_json 的类型化投影（APPLIED 时同事务写入）。 */
function courseIdOf(proposal: AgentProposalOut): string | null {
  return typeof proposal.result?.course_id === "string"
    ? proposal.result.course_id
    : null;
}
