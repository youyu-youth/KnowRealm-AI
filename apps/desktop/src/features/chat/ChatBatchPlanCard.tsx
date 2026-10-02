import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Check, X } from "lucide-react";

import { AgentRunProgress } from "@/features/agent/AgentRunProgress";
import { useCourseNames } from "@/features/chat/useCourseNames";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

const BATCH_PROPOSAL_TYPE = "OP_BATCH";

/** id 缩写兜底（课程名等查不到时显示，不造假名）。 */
function shortId(id: string): string {
  return `#${id.slice(0, 8)}`;
}

/** 计划项参数的输出引用（工单 06 结果绑定）：course_id 等参数值可为
 * {step, field} 引用对象（执行时由后端注入实际值），渲染前必须区分形态。 */
type StepOutputRef = { step?: unknown; field?: unknown };

type PlanItem = {
  action?: string;
  item_id?: string | null;
  title?: string | null;
  course_id?: string | StepOutputRef | null;
  name?: string | null;
  learning_context?: string | null;
  education_stage?: string | null;
  depth?: string | null;
  description?: string | null;
  url?: string | null;
  depends_on?: number[];
};

type PlanPayload = { items?: PlanItem[]; plan_version?: number };

type PlanSnapshot = { items?: { state?: { title?: string } }[] };

/** 输出引用的展示值（「第 N 步输出」，序号与依赖列一致 1 起）；非引用形态
 * 或形状异常（异常数据）返回 null（不崩渲染）。 */
function stepRefLabel(value: StepOutputRef, t: TFunction): string | null {
  const step = value.step;
  return typeof step === "number"
    ? t("chat.batchPlan.paramCourseFromStep", { index: step + 1 })
    : null;
}

/** 逐项目标名：优先确认卡预览投影（提交时固化的快照标题），否则载荷标题，
 * 再退回目标 id 缩写——不造假名。 */
function planItemTitle(
  proposal: AgentProposalOut,
  item: PlanItem,
  index: number,
): string {
  const snapshot = (proposal.snapshot ?? {}) as PlanSnapshot;
  const snapshotTitle = snapshot.items?.[index]?.state?.title;
  if (typeof snapshotTitle === "string" && snapshotTitle.trim()) {
    return snapshotTitle;
  }
  if (item.name?.trim()) {
    return item.name;
  }
  if (item.title?.trim()) {
    return item.title;
  }
  if (item.url?.trim()) {
    return item.url;
  }
  return item.item_id ? shortId(item.item_id) : "";
}

/** 批量整理计划卡（通用 Agent 第二阶段工单 05）：OP_BATCH 提案 = 批次授权载体。
 *
 * 待确认态整卡一次确认（批准的是对象集合＋逐项参数＋计划版本）；已确认态就地转
 * 任务进度（逐项结果 + 继续 / 重试 / 取消按钮，数据源与操作历史同一个 Run 查询）。
 * 计划修改后版本递增、需要重新确认（卡片显示版本提示）。提案本体唯一事实源在
 * 服务端：重启 / 断线后经本会话提案查询恢复视图。 */
export function ChatBatchPlanCard({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const courseNames = useCourseNames();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<
    Record<string, AgentProposalOut["status"]>
  >({});

  const { data } = useQuery({
    queryKey: libraryKeys.sessionProposals(sessionId),
    queryFn: () => libraryApi.listProposals({ session_id: sessionId }),
    staleTime: 0,
  });

  const plans = useMemo(
    () =>
      (data ?? []).filter(
        (proposal) =>
          proposal.proposal_type === BATCH_PROPOSAL_TYPE &&
          proposal.session_id === sessionId,
      ),
    [data, sessionId],
  );

  if (plans.length === 0) {
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
        setOverrides((current) => ({
          ...current,
          [proposalId]: result.status,
        }));
        void queryClient.invalidateQueries({
          queryKey: [...libraryKeys.all, "proposals"],
        });
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : String(exc));
        // 失败后回查真相（可能已实际应用或已落 FAILED）。
        void queryClient.invalidateQueries({
          queryKey: libraryKeys.sessionProposals(sessionId),
        });
      })
      .finally(() => setBusyId(null));
  };

  return (
    <section
      aria-label={t("chat.batchPlan.panelTitle")}
      className="border-border/60 mt-2 flex flex-col gap-2 rounded-md border px-3 py-2"
    >
      <p className="text-label text-muted-foreground">
        {t("chat.batchPlan.panelTitle")}
      </p>
      <ul className="flex flex-col gap-2">
        {plans.map((proposal) => {
          const status = overrides[proposal.id] ?? proposal.status;
          return (
            <li key={proposal.id} className="flex flex-col gap-2">
              {status === "PENDING" || status === "FAILED" ? (
                <ActionablePlan
                  proposal={proposal}
                  busy={busyId !== null}
                  courseNames={courseNames}
                  onDecide={decide}
                  t={t}
                />
              ) : (
                <SettledPlan proposal={proposal} status={status} t={t} />
              )}
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

/** 待确认态：逐项列出目标与参数 + 计划版本 + 整卡确认 / 拒绝。 */
function ActionablePlan({
  proposal,
  busy,
  courseNames,
  onDecide,
  t,
}: {
  proposal: AgentProposalOut;
  busy: boolean;
  courseNames: Map<string, string>;
  onDecide: (proposalId: string, accept: boolean) => void;
  t: TFunction;
}) {
  const payload = (proposal.payload ?? {}) as PlanPayload;
  const items = payload.items ?? [];
  const version = payload.plan_version ?? 1;
  const snapshotStale = proposal.error_code === "OPERATION_SNAPSHOT_STALE";
  return (
    <div className="bg-surface-subtle flex flex-col gap-2 rounded-md px-2.5 py-2">
      {proposal.status === "FAILED" ? (
        <p role="alert" className="text-destructive text-label">
          {proposal.error_code
            ? t(`chat.batchPlan.failedDetail`, {
                reason: t(`errors.${proposal.error_code}`, proposal.error_code),
              })
            : t("chat.batchPlan.failed")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-label font-label text-ink">
          {t("chat.batchPlan.itemCount", { count: items.length })}
        </span>
        <span className="text-label text-muted-foreground">
          {t("chat.batchPlan.version", { version })}
        </span>
        {version > 1 ? (
          <span className="text-label text-muted-foreground">
            {t("chat.batchPlan.replanHint")}
          </span>
        ) : null}
        <span className="min-w-0 flex-1" />
        {!snapshotStale ? (
          <Button
            size="xs"
            variant="outline"
            disabled={busy}
            onClick={() => onDecide(proposal.id, true)}
          >
            <Check data-icon="inline-start" aria-hidden="true" />
            {t("chat.batchPlan.accept")}
          </Button>
        ) : null}
        <Button
          size="xs"
          variant="ghost"
          disabled={busy}
          onClick={() => onDecide(proposal.id, false)}
        >
          <X data-icon="inline-start" aria-hidden="true" />
          {t("chat.batchPlan.reject")}
        </Button>
      </div>
      <ol className="flex flex-col gap-1">
        {items.map((item, index) => (
          <PlanItemRow
            key={`${item.action}-${item.item_id}-${index}`}
            item={item}
            target={planItemTitle(proposal, item, index)}
            courseNames={courseNames}
            t={t}
          />
        ))}
      </ol>
      <p className="text-label text-muted-foreground">
        {t("chat.batchPlan.hint")}
      </p>
    </div>
  );
}

/** 逐项目标行：动作 + 目标（快照标题优先）+ 参数（归类课程名查不到时回落 id
 * 缩写）+ 依赖（全部列出）。 */
function PlanItemRow({
  item,
  target,
  courseNames,
  t,
}: {
  item: PlanItem;
  target: string;
  courseNames: Map<string, string>;
  t: TFunction;
}) {
  // 授权参数必须可见：课程名解析失败（未加载 / 课程不在列表）回落 id 缩写；
  // 输出引用（对象）呈现来源步骤，不得当字符串截断（工单 06 真机回归）。
  const courseLabel =
    item.course_id == null
      ? ""
      : typeof item.course_id === "string"
        ? (courseNames.get(item.course_id) ?? shortId(item.course_id))
        : (stepRefLabel(item.course_id, t) ?? "");
  const params = [
    item.title ? t("chat.batchPlan.paramTitle", { title: item.title }) : "",
    courseLabel ? t("chat.batchPlan.paramCourse", { course: courseLabel }) : "",
    item.url && item.url !== target
      ? t("chat.batchPlan.paramUrl", { url: item.url })
      : "",
    ...(
      [
        [item.learning_context, "learningContext"],
        [item.education_stage, "educationStage"],
        [item.depth, "depth"],
      ] as const
    ).map(([value, key]) =>
      value
        ? t("chat.batchPlan.paramValue", {
            label: t(`spaces.form.${key}`),
            value: t(`spaces.${key}.${value}`, value),
          })
        : "",
    ),
    item.description
      ? t("chat.batchPlan.paramValue", {
          label: t("spaces.detail.label.description"),
          value: item.description,
        })
      : "",
  ].filter(Boolean);
  return (
    <li className="flex flex-wrap items-center gap-2">
      <span className="text-label text-muted-foreground shrink-0">
        {t("settings.operationHistory.action." + (item.action ?? ""), {
          defaultValue: item.action ?? "",
        })}
      </span>
      <span className="text-label min-w-0 flex-1 wrap-anywhere">{target}</span>
      {params.length > 0 ? (
        <span className="text-label text-muted-foreground min-w-0 wrap-anywhere">
          {params.join(" · ")}
        </span>
      ) : null}
      {item.depends_on && item.depends_on.length > 0 ? (
        <span className="text-label text-muted-foreground shrink-0">
          {t("chat.batchPlan.dependsOn", {
            indexes: item.depends_on.map((index) => String(index + 1)),
          })}
        </span>
      ) : null}
    </li>
  );
}

/** 已确认态：就地转任务进度（run_id 来自结果投影）；已拒绝为终态文案。 */
function SettledPlan({
  proposal,
  status,
  t,
}: {
  proposal: AgentProposalOut;
  status: AgentProposalOut["status"];
  t: TFunction;
}) {
  if (status === "REJECTED") {
    return (
      <p className="text-label text-muted-foreground">
        {t("chat.batchPlan.rejected")}
      </p>
    );
  }
  const runId = proposal.result?.["run_id"];
  if (typeof runId !== "string") {
    return (
      <p className="text-label text-muted-foreground">
        <Spinner aria-hidden="true" /> {t("chat.batchPlan.accepted")}
      </p>
    );
  }
  return <AgentRunProgress runId={runId} />;
}
