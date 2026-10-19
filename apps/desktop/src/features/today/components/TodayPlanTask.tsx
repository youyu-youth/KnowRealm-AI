import { Link, useNavigate } from "@tanstack/react-router";
import {
  BookOpen,
  CalendarClock,
  Check,
  ExternalLink,
  Timer,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { TodayItemMenu } from "@/features/today/components/TodayItemMenu";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { StatusTag } from "@/components/common/StatusTag";
import type { TodayPlanItem } from "@/features/today/api/today";

type Props = {
  item: TodayPlanItem;
  expanded?: boolean;
  selected: boolean;
  busy: boolean;
  disabled: boolean;
  onFocus: (id: string) => void;
  onComplete: (item: TodayPlanItem) => void;
};

export function TodayPlanTask({
  item,
  expanded = false,
  selected,
  busy,
  disabled,
  onFocus,
  onComplete,
}: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  return (
    <TodayItemMenu
      className={expanded ? "today-plan-card" : "today-task-row"}
      title={item.content}
      data-selected={selected}
      quickAction={!expanded}
      draggable={!expanded}
      onDragStart={(event) => {
        event.dataTransfer.setData(
          "application/x-knowrealm-plan-item",
          item.item_id,
        );
        event.dataTransfer.effectAllowed = "copy";
      }}
      actions={[
        {
          label: t("today.workspace.focusSelected"),
          icon: Timer,
          run: () => onFocus(item.item_id),
        },
        {
          label: t("today.workspace.openPlan"),
          icon: ExternalLink,
          run: () =>
            void navigate({
              to: "/spaces/$courseId",
              params: { courseId: item.course_id },
              search: { tab: "plan" },
            }),
        },
        {
          label: t("today.workspace.markComplete"),
          icon: Check,
          disabled: disabled,
          run: () => onComplete(item),
        },
      ]}
    >
      {!expanded && (
        <Checkbox
          aria-label={t("today.planTodos.completeLabel", {
            content: item.content,
          })}
          // 受控绑定未完成态（计划 Tab checked={done} 同构）：列表项
          // 本就只含待学项、完成即随缓存失效离开列表，恒 false 让
          // 失败回执后不可能残留假勾选（非受控点击即翻转，会与
          // 服务端 PENDING 不一致）。
          checked={false}
          disabled={disabled}
          onCheckedChange={() => onComplete(item)}
          className="mt-1"
        />
      )}
      <div className="today-plan-task-copy min-w-0 flex-1">
        <Link
          to="/spaces/$courseId"
          params={{ courseId: item.course_id }}
          search={{ tab: "plan" }}
          className="hover:text-today-accent block font-medium transition-colors"
          title={item.content}
        >
          <span
            className={expanded ? "today-plan-card-title" : "today-task-title"}
          >
            {item.content}
          </span>
        </Link>
        {expanded && (
          <p
            className="today-plan-card-goal text-label text-ink-muted mt-2"
            title={item.goal_title}
          >
            {item.goal_title}
          </p>
        )}
      </div>
      <span
        className="today-plan-task-course text-label text-ink-muted break-words"
        title={
          expanded
            ? item.course_name
            : `${item.course_name} · ${item.goal_title}`
        }
      >
        {expanded && (
          <BookOpen className="size-4 shrink-0" aria-hidden="true" />
        )}
        {expanded ? (
          item.course_name
        ) : (
          <>
            <span className="min-w-0 truncate">{item.course_name}</span>
            <span className="min-w-0 truncate"> · {item.goal_title}</span>
          </>
        )}
      </span>
      <div className="today-plan-task-meta text-label text-ink-muted">
        <p className="text-label text-muted-foreground mt-0.5 grid gap-1">
          {item.estimated_minutes != null || expanded ? (
            <span>
              {item.estimated_minutes == null
                ? t("today.progress.unestimated")
                : t("today.planTodos.minutes", {
                    minutes: item.estimated_minutes,
                  })}
            </span>
          ) : null}
          <span
            className="inline-flex items-center gap-0.5"
            title={t("today.planTodos.scheduledTitle")}
          >
            <CalendarClock aria-hidden="true" className="size-3" />
            {formatDueLabel(item.scheduled_date, i18n.resolvedLanguage, t)}
          </span>
        </p>
      </div>
      {busy ? (
        <span
          role="status"
          className="today-plan-task-status text-label text-ink-muted flex items-center gap-1"
        >
          <Spinner className="size-3" />
          {t("today.workspace.completing")}
        </span>
      ) : (
        <StatusTag
          className="today-plan-task-status"
          tone={isOverdue(item.scheduled_date) ? "warning" : "neutral"}
        >
          {t(
            isOverdue(item.scheduled_date)
              ? "today.planTodos.overdue"
              : "today.workspace.notStarted",
          )}
        </StatusTag>
      )}
      {expanded && (
        <div className="today-plan-card-actions">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onFocus(item.item_id)}
          >
            <Timer aria-hidden="true" />
            {t("today.workspace.focusSelected")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled}
            aria-label={t("today.planTodos.completeLabel", {
              content: item.content,
            })}
            onClick={() => onComplete(item)}
          >
            {busy ? (
              <Spinner aria-hidden="true" />
            ) : (
              <Check aria-hidden="true" />
            )}
            {t("today.workspace.markComplete")}
          </Button>
        </div>
      )}
    </TodayItemMenu>
  );
}

// 排期日是按日字符串：与「今日零点」直接比 Date 即得两档判断（逾期 / 即今天）。
function startOfDay(value: Date): number {
  return new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate(),
  ).getTime();
}

function isOverdue(scheduledDate: string): boolean {
  return (
    startOfDay(new Date(`${scheduledDate}T00:00:00`)) < startOfDay(new Date())
  );
}

// 排期日即今天显示「今天」，早于今天显示月日（逾期徽章另标）。
function formatDueLabel(
  scheduledDate: string,
  language: string | undefined,
  t: (key: string) => string,
): string {
  const due = new Date(`${scheduledDate}T00:00:00`);
  if (startOfDay(due) === startOfDay(new Date())) {
    return t("today.planTodos.today");
  }
  return new Intl.DateTimeFormat(language, {
    month: "short",
    day: "numeric",
  }).format(due);
}
