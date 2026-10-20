import { Link } from "@tanstack/react-router";
import type { components } from "@knowrealm/api-types";
import { Bot, Lock, MessageSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { toastMutationError } from "@/features/learningPlan/mutationError";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import {
  useLearningGoals,
  usePlanDetail,
  usePlanVersions,
  useCompletePlanItem,
  useSkipPlanItem,
  useUpdatePlanItem,
  type LearningGoal,
  type PlanDetail,
  type PlanItem,
  type PlanItemUpdateBody,
  type PlanVersion,
} from "@/features/learningPlan/api/learningPlan";
import {
  PLAN_ITEM_TYPE_KEYS,
  isPlanItemType,
} from "@/features/learningPlan/planItemTypes";
import { useRecordStudy } from "@/features/learningPlan/api/study";

type LearningPlanTabProps = { courseId: string; focusItemId?: string };

type GoalStatus = components["schemas"]["GoalStatus"];

// 目标状态徽章文案（GoalCard 展示与生成枚举联动，planItemTypes 同式）。
const GOAL_STATUS_LABEL_KEYS: Record<GoalStatus, string> = {
  ACTIVE: "learningPlan.goalCard.activeGoal",
  COMPLETED: "learningPlan.goalCard.completedGoal",
  ARCHIVED: "learningPlan.goalCard.archivedGoal",
};

/** 学习计划 Tab（工单 04）：目标卡 + 版本切换 + 阶段分组计划项 + 项级执行面。
 *
 * 读取面与执行面全部走工单 03 已就位的课程嵌套端点；历史版本只读查看（编辑 /
 * 完成 / 跳过仅当前生效版本可用）。完结 / 归档的目标保留只读查看入口（spec
 * 用户故事 16 的追溯要求）：默认仍跟随进行中目标（日常执行面），无进行中目标
 * 时回落最近的历史目标只读展示，并保留"设定新目标"引导。空态两档：完全无目标
 * → 引导对话设定目标（新建目标主路径＝对话，本 Tab 为手动兜底与日常执行面）；
 * 有目标无计划 → 引导对话生成计划草案。 */
export function LearningPlanTab({
  courseId,
  focusItemId,
}: LearningPlanTabProps) {
  const { t } = useTranslation();
  const goals = useLearningGoals(courseId);
  const focused = useRecordStudy(focusItemId);
  const focus = focused.data?.course_id === courseId ? focused.data : undefined;
  // null = 跟随默认目标（进行中优先）；显式选择后固定该目标。
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);

  if (goals.isPending) {
    return (
      <p
        role="status"
        className="text-body text-ink-muted flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("learningPlan.loading")}
      </p>
    );
  }
  if (goals.isError) {
    return (
      <QueryError
        title={t("learningPlan.errorTitle")}
        description={t("learningPlan.errorDescription")}
        retryLabel={t("learningPlan.retry")}
        onRetry={() => void goals.refetch()}
      />
    );
  }

  const activeGoal = goals.data?.find((goal) => goal.status === "ACTIVE");
  // 后端按"进行中在前、其余更新时间倒序"返回：首个非 ACTIVE 即最近的历史
  // 目标，作为无进行中目标时的只读回落。
  const fallbackGoal = goals.data?.find((goal) => goal.status !== "ACTIVE");
  const currentGoal =
    goals.data?.find((goal) => goal.id === selectedGoalId) ??
    goals.data?.find((goal) => goal.id === focus?.goal_id) ??
    activeGoal ??
    fallbackGoal;

  if (!currentGoal) {
    return (
      <GuideCard
        title={t("learningPlan.emptyGoal.title")}
        description={t("learningPlan.emptyGoal.description")}
        action={t("learningPlan.emptyGoal.cta")}
      />
    );
  }
  return (
    <div className="grid gap-6">
      {/* key 重挂载：切换目标后版本选择状态随目标重置（各目标版本互不相干）。 */}
      <GoalWorkspace
        key={currentGoal.id}
        courseId={courseId}
        goal={currentGoal}
        goals={goals.data ?? []}
        onGoalChange={setSelectedGoalId}
        focusedPlanId={focus?.plan_id}
        focusItemId={focusItemId}
      />
      {activeGoal == null ? (
        <GuideCard
          title={t("learningPlan.emptyGoal.title")}
          description={t("learningPlan.emptyGoal.description")}
          action={t("learningPlan.emptyGoal.cta")}
        />
      ) : null}
    </div>
  );
}

function GoalWorkspace({
  courseId,
  goal,
  goals,
  onGoalChange,
  focusedPlanId,
  focusItemId,
}: {
  courseId: string;
  goal: LearningGoal;
  goals: LearningGoal[];
  onGoalChange: (goalId: string) => void;
  focusedPlanId?: string;
  focusItemId?: string;
}) {
  const { t } = useTranslation();
  const versions = usePlanVersions(courseId, goal.id);
  // null = 跟随生效版本（默认视图）；切换后显式选中历史版本（只读）。
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);

  const activeVersion = versions.data?.find(
    (version) => version.status === "ACTIVE",
  );
  const currentPlanId =
    selectedPlanId ?? focusedPlanId ?? activeVersion?.id ?? null;
  const plan = usePlanDetail(courseId, currentPlanId);

  if (versions.isError) {
    return (
      <QueryError
        title={t("learningPlan.errorTitle")}
        description={t("learningPlan.errorDescription")}
        retryLabel={t("learningPlan.retry")}
        onRetry={() => void versions.refetch()}
      />
    );
  }
  if (versions.isPending) {
    return (
      <>
        <GoalCard goal={goal} progress={null} />
        <p
          role="status"
          className="text-body text-ink-muted mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("learningPlan.loading")}
        </p>
      </>
    );
  }
  if (!versions.data || versions.data.length === 0) {
    return (
      <>
        <GoalCard goal={goal} progress={null} />
        <GuideCard
          title={t("learningPlan.emptyPlan.title")}
          description={t("learningPlan.emptyPlan.description")}
          action={t("learningPlan.emptyPlan.cta")}
          className="mt-6"
        />
      </>
    );
  }

  const items = plan.data?.items;
  const done = items?.filter((item) => item.status === "DONE").length;
  const isCurrent = plan.data?.status === "ACTIVE";
  // 历史版本只读；完结 / 归档目标的执行面整体只读（其计划不再催办，今日
  // 待学同口径排除非 ACTIVE 目标）。
  const editable = goal.status === "ACTIVE" && isCurrent !== false;

  return (
    <div className="grid gap-6">
      {goals.length > 1 ? (
        <div className="flex justify-end">
          <Select
            items={goals.map((goal) => goalLabel(goal, t))}
            value={goal.id}
            onValueChange={(value) => onGoalChange(String(value))}
          >
            <SelectTrigger
              size="sm"
              className="min-w-44"
              aria-label={t("learningPlan.goalSelect.label")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {goals.map((goal) => (
                <SelectItem key={goal.id} value={goal.id}>
                  {goalLabel(goal, t).label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      <GoalCard
        goal={goal}
        progress={
          items != null && done != null ? { done, total: items.length } : null
        }
      />
      <section
        aria-label={t("learningPlan.version.sectionLabel")}
        className="bg-surface-raised border-border-subtle rounded-md border"
      >
        <div className="border-border-subtle flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="text-section font-section text-ink-strong">
              {t("learningPlan.version.sectionTitle")}
            </h2>
            {isCurrent === false ? (
              <StatusTag>{t("learningPlan.version.readonly")}</StatusTag>
            ) : null}
          </div>
          <Select
            items={versions.data.map((version) => versionLabel(version, t))}
            value={currentPlanId ?? undefined}
            onValueChange={(value) => setSelectedPlanId(String(value))}
          >
            <SelectTrigger
              size="sm"
              className="min-w-44"
              aria-label={t("learningPlan.version.selectLabel")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {versions.data.map((version) => (
                <SelectItem key={version.id} value={version.id}>
                  {versionLabel(version, t).label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <PlanBody
          courseId={courseId}
          isPending={plan.isPending}
          isError={plan.isError}
          onRetry={() => void plan.refetch()}
          plan={plan.data}
          editable={editable}
          focusItemId={focusItemId}
        />
      </section>
    </div>
  );
}

function PlanBody({
  courseId,
  isPending,
  isError,
  onRetry,
  plan,
  editable,
  focusItemId,
}: {
  courseId: string;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  plan: PlanDetail | undefined;
  editable: boolean;
  focusItemId?: string;
}) {
  const { t } = useTranslation();

  if (isPending) {
    return (
      <p
        role="status"
        className="text-body text-ink-muted flex items-center gap-2 px-5 py-6"
      >
        <Spinner aria-hidden="true" />
        {t("learningPlan.loading")}
      </p>
    );
  }
  if (isError || !plan) {
    return (
      <div className="px-5 py-6">
        <QueryError
          title={t("learningPlan.errorTitle")}
          description={t("learningPlan.errorDescription")}
          retryLabel={t("learningPlan.retry")}
          onRetry={onRetry}
        />
      </div>
    );
  }

  return (
    <div className="px-5 py-5">
      {groupByPhase(plan.items).map(([title, items]) => (
        <section key={title} className="mt-6 first:mt-0" aria-label={title}>
          <h3 className="text-body-dense text-ink-strong font-medium">
            {title}
          </h3>
          <ul className="divide-border-subtle mt-2 divide-y">
            {items.map((item) => (
              <PlanItemRow
                key={item.id}
                courseId={courseId}
                planId={plan.id}
                item={item}
                editable={editable}
                focused={item.id === focusItemId}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** 计划项行：勾选完成 / 跳过 / 内联编辑（改日期、时长、内容）。
 *
 * 编辑与执行仅 editable（当前生效版本）时出现；DONE 行复选框置选且不可再改
 * （完成单向，无取消完成入口），SKIPPED 行淡化呈现。 */
function PlanItemRow({
  courseId,
  planId,
  item,
  editable,
  focused,
}: {
  courseId: string;
  planId: string;
  item: PlanItem;
  editable: boolean;
  focused?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const row = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (!focused) return;
    row.current?.focus();
    row.current?.scrollIntoView?.({ block: "nearest" });
  }, [focused]);
  const [editing, setEditing] = useState(false);
  const complete = useCompletePlanItem();
  const skip = useSkipPlanItem(courseId);
  const update = useUpdatePlanItem(courseId);
  const busy =
    (complete.isPending && complete.variables?.itemId === item.id) ||
    (skip.isPending && skip.variables?.itemId === item.id);

  if (editing && editable) {
    return (
      <li className="py-3">
        <PlanItemEditRow
          item={item}
          savePending={update.isPending}
          onSave={(body) =>
            update.mutate(
              { planId, itemId: item.id, body },
              {
                onSuccess: () => setEditing(false),
                onError: (error) =>
                  toastMutationError(error, t("learningPlan.mutationFailed")),
              },
            )
          }
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  const done = item.status === "DONE";
  const skipped = item.status === "SKIPPED";
  return (
    <li
      ref={row}
      tabIndex={-1}
      className="focus-visible:ring-ring flex min-w-0 items-start gap-3 rounded-sm py-3 focus-visible:ring-2"
    >
      <Checkbox
        aria-label={t("learningPlan.item.completeLabel", {
          content: item.content,
        })}
        checked={done}
        disabled={!editable || done || skipped || busy}
        onCheckedChange={() =>
          complete.mutate(
            { courseId, planId, itemId: item.id },
            {
              onError: (error) =>
                toastMutationError(error, t("learningPlan.mutationFailed")),
            },
          )
        }
        className="mt-1"
      />
      <div className="min-w-0 flex-1">
        <p
          className={
            skipped
              ? "text-body text-ink-faint line-through"
              : "text-body text-ink-strong"
          }
        >
          {item.content}
        </p>
        <p className="text-label text-ink-muted mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusTag>{itemActionLabel(item.action_type, t)}</StatusTag>
          <span>
            {formatShortDate(item.scheduled_date, i18n.resolvedLanguage)}
          </span>
          {item.estimated_minutes != null ? (
            <span>
              {t("learningPlan.item.minutes", {
                minutes: item.estimated_minutes,
              })}
            </span>
          ) : null}
          {item.user_locked ? (
            <span
              className="inline-flex items-center gap-0.5"
              title={t("learningPlan.item.lockedTitle")}
            >
              <Lock aria-hidden="true" className="size-3" />
              {t("learningPlan.item.locked")}
            </span>
          ) : null}
          {done ? <span>{t("learningPlan.item.done")}</span> : null}
          {skipped ? <span>{t("learningPlan.item.skipped")}</span> : null}
        </p>
        {item.reason ? (
          <p className="text-label text-ink-faint mt-1" title={item.reason}>
            {item.reason}
          </p>
        ) : null}
        {item.action_type === "STUDY_RECORD" ? (
          <Link
            to="/plan-items/$itemId/study"
            params={{ itemId: item.id }}
            className={buttonVariants({
              variant: "outline",
              size: "sm",
              className: "mt-3",
            })}
          >
            {t(editable && !skipped ? "study.openItem" : "study.viewResult")}
          </Link>
        ) : null}
        {item.action_type === "PRACTICE_QUIZ" ? (
          <Link
            to="/plan-items/$itemId/practice"
            params={{ itemId: item.id }}
            className={buttonVariants({
              variant: "outline",
              size: "sm",
              className: "mt-3",
            })}
          >
            {t("practice.title")}
          </Link>
        ) : null}
      </div>
      {editable && !done && !skipped ? (
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => setEditing(true)}
          >
            {t("learningPlan.item.edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() =>
              skip.mutate(
                { planId, itemId: item.id },
                {
                  onError: (error) =>
                    toastMutationError(error, t("learningPlan.mutationFailed")),
                },
              )
            }
          >
            {t("learningPlan.item.skip")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

/** 内联编辑行：日期 / 时长 / 内容三输入 + 保存取消（PATCH 至少一字段，
 * 未变更字段不下发）。 */
function PlanItemEditRow({
  item,
  onSave,
  onCancel,
  savePending,
}: {
  item: PlanItem;
  onSave: (body: PlanItemUpdateBody) => void;
  onCancel: () => void;
  savePending: boolean;
}) {
  const { t } = useTranslation();
  const [date, setDate] = useState(item.scheduled_date);
  const [minutes, setMinutes] = useState(
    item.estimated_minutes != null ? String(item.estimated_minutes) : "",
  );
  const [content, setContent] = useState(item.content);

  // 仅提交变更字段（PATCH 至少一字段）：无变更时禁用保存，不发会被后端
  // _require_any_field 拒绝的空载荷。
  const changes: PlanItemUpdateBody = {
    ...(date !== item.scheduled_date ? { scheduled_date: date } : {}),
    ...(minutes !== "" && Number(minutes) !== item.estimated_minutes
      ? { estimated_minutes: Number(minutes) }
      : {}),
    ...(content.trim() !== item.content ? { content: content.trim() } : {}),
  };
  const hasChanges = Object.keys(changes).length > 0;

  return (
    <div className="grid gap-2">
      <Input
        aria-label={t("learningPlan.edit.contentLabel")}
        value={content}
        maxLength={200}
        onChange={(event) => setContent(event.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="date"
          aria-label={t("learningPlan.edit.dateLabel")}
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="w-40"
        />
        <Input
          type="number"
          min={1}
          max={600}
          aria-label={t("learningPlan.edit.minutesLabel")}
          value={minutes}
          placeholder={t("learningPlan.edit.minutesPlaceholder")}
          onChange={(event) => setMinutes(event.target.value)}
          className="w-24"
        />
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="sm"
            disabled={savePending || !content.trim() || !date || !hasChanges}
            onClick={() => onSave(changes)}
          >
            {t("learningPlan.edit.save")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={savePending}
            onClick={onCancel}
          >
            {t("learningPlan.edit.cancel")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function GoalCard({
  goal,
  progress,
}: {
  goal: LearningGoal;
  progress: { done: number; total: number } | null;
}) {
  const { t, i18n } = useTranslation();
  const deadline = goal.target_date
    ? new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        year: "numeric",
        month: "long",
        day: "numeric",
      }).format(new Date(`${goal.target_date}T00:00:00`))
    : null;
  return (
    <section
      aria-label={t("learningPlan.goalCard.label")}
      className="bg-surface-raised border-border-subtle rounded-md border px-5 py-4"
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusTag>
              {t(`learningPlan.goalType.${goal.goal_type}`)}
            </StatusTag>
            <span className="text-label text-ink-muted">
              {t(GOAL_STATUS_LABEL_KEYS[goal.status])}
            </span>
          </div>
          <h2 className="text-section font-section text-ink-strong mt-2">
            {goal.title}
          </h2>
        </div>
        <dl className="text-label text-ink-muted grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-3">
          <div>
            <dt className="text-ink-faint">
              {t("learningPlan.goalCard.deadline")}
            </dt>
            <dd className="text-ink-strong mt-0.5">
              {deadline ?? t("learningPlan.goalCard.unset")}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">
              {t("learningPlan.goalCard.dailyMinutes")}
            </dt>
            <dd className="text-ink-strong mt-0.5">
              {goal.daily_minutes != null
                ? t("learningPlan.goalCard.dailyMinutesValue", {
                    minutes: goal.daily_minutes,
                  })
                : t("learningPlan.goalCard.unset")}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">
              {t("learningPlan.goalCard.progress")}
            </dt>
            <dd className="text-ink-strong mt-0.5">
              {progress
                ? t("learningPlan.goalCard.progressValue", {
                    done: progress.done,
                    total: progress.total,
                  })
                : t("learningPlan.goalCard.progressEmpty")}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function GuideCard({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description: string;
  action: string;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <section
      className={`bg-surface-raised border-border-subtle rounded-md border px-5 py-10 text-center ${className ?? ""}`}
    >
      <MessageSquare
        aria-hidden="true"
        className="text-ink-muted mx-auto size-6"
      />
      <h2 className="text-section font-section text-ink-strong mt-3">
        {title}
      </h2>
      <p className="text-body text-ink-muted max-w-reading mx-auto mt-2">
        {description}
      </p>
      <Link to="/chat" className={buttonVariants({ className: "mt-6" })}>
        <Bot aria-hidden="true" className="size-4" />
        {action}
      </Link>
      <p className="text-label text-ink-faint mt-3">
        {t("learningPlan.guide.chatHint")}
      </p>
    </section>
  );
}

function QueryError({
  title,
  description,
  retryLabel,
  onRetry,
}: {
  title: string;
  description: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div role="alert">
      <h3 className="text-body-dense text-destructive font-medium">{title}</h3>
      <p className="text-label text-ink-muted mt-1">
        {description}
        <button
          type="button"
          className="text-ink ml-2 underline-offset-2 hover:underline"
          onClick={onRetry}
        >
          {retryLabel}
        </button>
      </p>
    </div>
  );
}

// action_type 是生成枚举经字符串列落库：收窄后才可索引文案映射（工单 03 先例）。
function itemActionLabel(
  actionType: string,
  t: (key: string) => string,
): string {
  return t(
    PLAN_ITEM_TYPE_KEYS[isPlanItemType(actionType) ? actionType : "CUSTOM"],
  );
}

function groupByPhase(items: PlanItem[]): Array<[string, PlanItem[]]> {
  const phases: Array<[string, PlanItem[]]> = [];
  for (const item of items) {
    const last = phases[phases.length - 1];
    if (last && last[0] === item.phase_title) {
      last[1].push(item);
    } else {
      phases.push([item.phase_title, [item]]);
    }
  }
  return phases;
}

/** 版本选项文案（Select items 与 SelectItem 共用一份，防两处改漏）。 */
function versionLabel(
  version: PlanVersion,
  t: (key: string, options?: Record<string, unknown>) => string,
): { value: string; label: string } {
  return {
    value: version.id,
    label:
      version.status === "ACTIVE"
        ? t("learningPlan.version.activeOption", {
            version: version.plan_version,
          })
        : t("learningPlan.version.historyOption", {
            version: version.plan_version,
          }),
  };
}

/** 目标选项文案（目标切换 Select 两处共用一份，versionLabel 同式）。 */
function goalLabel(
  goal: LearningGoal,
  t: (key: string, options?: Record<string, unknown>) => string,
): { value: string; label: string } {
  return {
    value: goal.id,
    label:
      goal.status === "ACTIVE"
        ? t("learningPlan.goalSelect.activeOption", { title: goal.title })
        : t("learningPlan.goalSelect.historyOption", { title: goal.title }),
  };
}

function formatShortDate(value: string, language: string | undefined): string {
  const date = new Date(`${value}T00:00:00`);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return new Intl.DateTimeFormat(language, {
    ...(sameYear ? {} : { year: "numeric" }),
    month: "short",
    day: "numeric",
  }).format(date);
}
