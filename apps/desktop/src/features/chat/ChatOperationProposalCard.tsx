import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Check, X } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import { Button } from "@/components/ui/button";

type ChatOperationProposalCardProps = {
  sessionId: string;
};

/** 本卡涵盖的操作提案类型（02 课程创建 / 03 向课程添加文本记录）。 */
const OPERATION_PROPOSAL_TYPES = new Set(["COURSE_CREATE", "TEXT_RECORD_ADD"]);

/** 确认/拒绝成功后的即时覆盖层：免去等 refetch 的空窗闪烁；远端到位后两者一致。 */
type DecisionOverride = {
  status: "APPLIED" | "REJECTED";
  result: Record<string, unknown> | null;
};

/** 操作卡文案键：按提案类型分发（课程创建走外层键、文本记录走 textRecord 子段）。 */
function labelKey(proposal: AgentProposalOut, key: string): string {
  return proposal.proposal_type === "TEXT_RECORD_ADD"
    ? `chat.operationProposal.textRecord.${key}`
    : `chat.operationProposal.${key}`;
}

/** 提案 payload → 课程创建确认卡字段行（标签复用新建课程表单文案，枚举值走既有翻译）。 */
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

/** TEXT_RECORD_ADD 正文摘要：折叠空白并截断到单行可读长度（全文在记录页）。 */
function contentExcerpt(content: unknown): string | null {
  if (typeof content !== "string" || !content.trim()) return null;
  const flat = content.replace(/\s+/g, " ").trim();
  return flat.length > 120 ? `${flat.slice(0, 120)}…` : flat;
}

/** 提案 payload / result 投影的字符串窄化（形状漂移时返回 null 兜底）。 */
function fieldString(
  source: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = source?.[key];
  return typeof value === "string" ? value : null;
}

/** 回执总结任务三态（spec 决策 15：已保存 ≠ 总结已生成 ≠ 可检索）：
 * 提交成功 → 已提交生成中；提交失败 → 失败原因 + 记录页重试指引；均无 → 未触发
 * （AI 未配置或未同意外发，读取 result 投影的窄化字段）。 */
function summaryStateText(
  result: Record<string, unknown> | null,
  t: TFunction,
): string {
  const summaryJobId = fieldString(result, "summary_job_id");
  const summaryErrorCode = fieldString(result, "summary_error_code");
  if (summaryJobId) {
    return t("chat.operationProposal.textRecord.summaryJobSubmitted");
  }
  if (summaryErrorCode) {
    return t("chat.operationProposal.textRecord.summaryFailed", {
      reason: t(`errors.${summaryErrorCode}`, summaryErrorCode),
    });
  }
  return t("chat.operationProposal.textRecord.summaryNotTriggered");
}

/** TEXT_RECORD_ADD 确认卡的目标课程名：经既有课程 API 按 id 拉取（spec 决策 14，
 * 确认卡预览不交付课程详情读取工具）；课程已删/不可读时如实提示。 */
function TextRecordCourseName({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: courseKeys.detail(courseId),
    queryFn: () => courseApi.get(courseId),
    staleTime: 30_000,
    retry: false,
  });
  if (query.isError) {
    return (
      <span className="text-muted-foreground">
        {t("chat.operationProposal.textRecord.courseUnavailable")}
      </span>
    );
  }
  return <>{query.data?.name ?? courseId}</>;
}

/** 确认卡字段行组（dl 内）：课程创建 = 完整参数行；文本记录 = 目标课程 + 正文摘要
 * + 明示「保存后将尝试生成 AI 总结」（spec 用户故事 9）。 */
function ProposalPreviewFields({
  proposal,
  t,
}: {
  proposal: AgentProposalOut;
  t: TFunction;
}) {
  if (proposal.proposal_type === "TEXT_RECORD_ADD") {
    const payload = proposal.payload ?? {};
    const targetCourseId = fieldString(payload, "course_id");
    const excerpt = contentExcerpt(payload.content);
    return (
      <>
        <div className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {t("chat.operationProposal.textRecord.targetCourse")}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">
            {targetCourseId ? (
              <TextRecordCourseName courseId={targetCourseId} />
            ) : null}
          </dd>
        </div>
        {excerpt ? (
          <div className="flex gap-2">
            <dt className="text-label text-muted-foreground shrink-0">
              {t("chat.operationProposal.textRecord.content")}
            </dt>
            <dd className="text-label text-ink min-w-0 break-words">
              {excerpt}
            </dd>
          </div>
        ) : null}
        <p className="text-label text-muted-foreground">
          {t("chat.operationProposal.textRecord.confirmHint")}
        </p>
      </>
    );
  }
  return (
    <>
      {previewRows(proposal.payload ?? {}, t).map((row) => (
        <div key={row.label} className="flex gap-2">
          <dt className="text-label text-muted-foreground shrink-0">
            {row.label}
          </dt>
          <dd className="text-label text-ink min-w-0 break-words">
            {row.value}
          </dd>
        </div>
      ))}
    </>
  );
}

/** 已决（APPLIED/REJECTED）回执行：按提案类型渲染入口跳转与总结任务真实状态。 */
function SettledProposalRow({
  proposal,
  status,
  result,
  t,
}: {
  proposal: AgentProposalOut;
  status: AgentProposalOut["status"];
  result: Record<string, unknown> | null;
  t: TFunction;
}) {
  const applied = status === "APPLIED";
  if (proposal.proposal_type === "TEXT_RECORD_ADD") {
    const recordId = fieldString(result, "record_id");
    return (
      <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
        <p className="text-label text-muted-foreground">
          {t(labelKey(proposal, applied ? "accepted" : "rejected"))}
        </p>
        {applied ? (
          <p className="text-label text-muted-foreground">
            {summaryStateText(result, t)}
          </p>
        ) : null}
        {applied && recordId ? (
          <Link
            to="/records/$recordId"
            params={{ recordId }}
            className="text-ink hover:bg-surface-raised text-label flex w-fit items-center gap-1 rounded px-1 py-0.5"
          >
            {t("chat.operationProposal.textRecord.openRecord")}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        ) : null}
      </div>
    );
  }
  const courseId = fieldString(result, "course_id");
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-2.5 py-1.5">
      <p className="text-label text-muted-foreground">
        {t(labelKey(proposal, applied ? "accepted" : "rejected"))}
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
}

/** 待确认/FAILED 可重试行：失败原因 + 参数预览 + 确认/拒绝按钮。 */
function ActionableProposalRow({
  proposal,
  status,
  busy,
  onDecide,
  t,
}: {
  proposal: AgentProposalOut;
  status: AgentProposalOut["status"];
  busy: boolean;
  onDecide: (proposalId: string, accept: boolean) => void;
  t: TFunction;
}) {
  const reason = proposal.error_code
    ? t(`errors.${proposal.error_code}`, proposal.error_code)
    : null;
  return (
    <li className="bg-surface-subtle flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1.5">
      {status === "FAILED" ? (
        <p role="alert" className="text-destructive text-label w-full">
          {reason
            ? t(labelKey(proposal, "failedDetail"), { reason })
            : t(labelKey(proposal, "failed"))}
        </p>
      ) : null}
      <dl className="min-w-0 flex-1">
        <ProposalPreviewFields proposal={proposal} t={t} />
      </dl>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={t(labelKey(proposal, "accept"))}
        disabled={busy}
        onClick={() => onDecide(proposal.id, true)}
      >
        <Check className="size-3.5" aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={t(labelKey(proposal, "reject"))}
        disabled={busy}
        onClick={() => onDecide(proposal.id, false)}
      >
        <X className="size-3.5" aria-hidden="true" />
      </Button>
    </li>
  );
}

/** 消息流内的操作提案就地确认卡（通用 Agent 第一阶段工单 02/03）：
 * 模型经写工具创建的 COURSE_CREATE / TEXT_RECORD_ADD 提案，完整参数预览后确认
 * （真实执行）或拒绝（零业务事实）；APPLIED 后转回执态——课程创建提供课程
 * 入口跳转，文本记录提供记录入口 + 总结任务真实状态（已提交 ≠ 未触发 ≠ 提交
 * 失败，spec 决策 15）。提案本体唯一事实源是服务端（agent_proposals 表）：
 * 断线/重启经本会话全状态提案查询恢复状态视图（工单 02 review）——APPLIED 的
 * 回执、FAILED 的失败原因与重试、REJECTED 的终态文案均由查询还原，不依赖组件内存。 */
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
          OPERATION_PROPOSAL_TYPES.has(proposal.proposal_type) &&
          proposal.session_id === sessionId,
      ),
    [sessionProposals, sessionId],
  );

  if (proposals.length === 0) {
    return null;
  }
  const statusOf = (proposal: AgentProposalOut): AgentProposalOut["status"] =>
    overrides[proposal.id]?.status ?? proposal.status;
  const resultOf = (
    proposal: AgentProposalOut,
  ): Record<string, unknown> | null =>
    overrides[proposal.id]?.result ?? proposal.result ?? null;
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
            result: result.result ?? null,
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
      {settled.map((proposal) => (
        <SettledProposalRow
          key={proposal.id}
          proposal={proposal}
          status={statusOf(proposal)}
          result={resultOf(proposal)}
          t={t}
        />
      ))}
      <ul className="flex flex-col gap-1.5">
        {actionable.map((proposal) => (
          <ActionableProposalRow
            key={proposal.id}
            proposal={proposal}
            status={statusOf(proposal)}
            busy={busyId !== null}
            onDecide={decide}
            t={t}
          />
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
