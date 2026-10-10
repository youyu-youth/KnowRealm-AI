import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpenText,
  CalendarClock,
  ChevronDown,
  FileText,
  Layers3,
  Mic,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { StatusTag } from "@/components/common/StatusTag";
import type { Course } from "@/features/courses/api/types";
import { CourseAvatar } from "@/features/courses/components/CourseCard";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";
import {
  mockActivities,
  mockPendingItems,
  mockRecentCourses,
  mockSpacesOverview,
  type SpacesActivity,
  type SpacesCourseInsight,
} from "@/features/courses/spacesInsights";

const statItems = [
  {
    key: "courseCount",
    icon: BookOpenText,
  },
  {
    key: "knowledgePointCount",
    icon: Layers3,
  },
  {
    key: "recordCount",
    icon: FileText,
  },
  {
    key: "activeThisWeek",
    icon: CalendarClock,
  },
] as const;

type SpacesInsightsRailProps = {
  courses: Course[];
};

export function SpacesInsightsRail({ courses }: SpacesInsightsRailProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const overview = mockSpacesOverview(courses);
  const recent = mockRecentCourses(courses, 4);
  const activities = mockActivities(courses, 5);

  return (
    <div className="grid gap-2" data-expanded={expanded || undefined}>
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger
          render={<Button variant="ghost" size="sm" />}
          className="group"
        >
          <BookOpenText aria-hidden="true" />
          {t("spaces.insights.label")}
          <ChevronDown
            aria-hidden="true"
            className="group-data-[panel-open]:rotate-180"
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-2 grid gap-3 md:grid-cols-2">
            <InsightsCard title={t("spaces.insights.stats.title")}>
              <dl className="mt-3 grid grid-cols-2 gap-3">
                {statItems.map(({ key, icon: Icon }) => (
                  <div key={key} className="flex items-center gap-2">
                    <Icon
                      className="text-ink-muted size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <dd className="text-section text-ink-strong font-semibold tabular-nums">
                        {overview[key]}
                      </dd>
                      <dt className="text-label text-ink-muted">
                        {t(`spaces.insights.stats.${key}`)}
                      </dt>
                    </div>
                  </div>
                ))}
              </dl>
            </InsightsCard>
            <InsightsCard title={t("spaces.insights.recent.title")}>
              {recent.length > 0 ? (
                <ol className="mt-3 grid gap-3">
                  {recent.map((insight, index) => (
                    <RecentCourseRow
                      key={insight.course.id}
                      insight={insight}
                      index={index + 1}
                    />
                  ))}
                </ol>
              ) : (
                <p className="text-label text-ink-muted mt-3">
                  {t("spaces.insights.recent.empty")}
                </p>
              )}
            </InsightsCard>
            <InsightsCard title={t("spaces.insights.activity.title")}>
              <ol className="mt-3 grid gap-2">
                {activities.map((activity) => (
                  <ActivityRow key={activity.id} activity={activity} />
                ))}
              </ol>
            </InsightsCard>
          </div>
        </CollapsibleContent>
      </Collapsible>
      <div className="spaces-dock">
        <section className="spaces-pending-section min-w-0">
          <header className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-spaces-section text-ink-strong font-semibold">
                {t("spaces.insights.pending.title")}
              </h2>
              <StatusTag>{t("spaces.insights.sample")}</StatusTag>
            </div>
            <Link
              to="/inbox"
              className="text-label text-ink-muted hover:text-ink-strong inline-flex items-center gap-1"
            >
              {t("spaces.dock.openInbox")}
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </header>
          <p className="text-label text-ink-muted mt-1">
            {mockPendingItems
              .map(
                (item) =>
                  `${t(`spaces.insights.pending.${item.key}`)} ${item.count}`,
              )
              .join(" · ")}
          </p>
          <ul className="spaces-pending-files">
            {(["note", "document", "audio"] as const).map((key) => {
              const Icon = key === "audio" ? Mic : FileText;
              return (
                <li key={key} className="spaces-file-preview">
                  <Icon
                    className="text-ink-muted size-5 shrink-0"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p
                      className="text-label text-ink-strong truncate font-medium"
                      title={t(`spaces.dock.files.${key}`)}
                    >
                      {t(`spaces.dock.files.${key}`)}
                    </p>
                    <p className="text-label text-ink-muted mt-1">
                      {t("spaces.dock.preview")}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-label text-ink-muted">
            {t("spaces.dock.classifyHint")}
          </p>
        </section>
        <section className="border-border min-w-0 border-t pt-3 @min-[55rem]/spaces:border-t-0">
          <header className="flex flex-wrap items-center gap-2">
            <h2 className="text-spaces-section text-ink-strong font-semibold">
              {t("spaces.insights.activity.title")}
            </h2>
            <StatusTag>{t("spaces.insights.sample")}</StatusTag>
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
            >
              {t("spaces.insights.viewAll")}
            </Button>
          </header>
          {activities.length > 0 ? (
            <ol className="mt-3 grid gap-2">
              {activities.slice(0, 2).map((activity) => (
                <ActivityRow key={activity.id} activity={activity} />
              ))}
            </ol>
          ) : (
            <p className="text-label text-ink-muted mt-3">
              {t("spaces.insights.activity.empty")}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function InsightsCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section className="border-border bg-surface-raised rounded-xl border p-4">
      <header className="flex min-w-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-section font-section text-ink-strong truncate">
            {title}
          </h2>
          <StatusTag className="shrink-0">
            {t("spaces.insights.sample")}
          </StatusTag>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function RecentCourseRow({
  insight,
  index,
}: {
  insight: SpacesCourseInsight;
  index: number;
}) {
  const { t, i18n } = useTranslation();
  const time = formatCourseMoment(
    activityDate(
      insight.lastActiveDaysAgo,
      insight.lastActiveHour,
      insight.lastActiveMinute,
    ),
    t("spaces.time.yesterdayAt"),
    i18n.resolvedLanguage ?? "zh-CN",
  );
  return (
    <li className="flex min-w-0 items-center gap-2.5">
      <span className="text-label text-ink-muted w-3 shrink-0 tabular-nums">
        {index}
      </span>
      <CourseAvatar context={insight.course.learning_context} size="sm" />
      <div className="min-w-0 flex-1">
        <p
          className="text-body-dense text-ink-strong truncate font-medium"
          title={insight.course.name}
        >
          {insight.course.name}
        </p>
        <p className="text-label text-ink-muted mt-0.5">
          {time}
          {" · "}
          {t(`spaces.insights.recent.${insight.activityKind}`, {
            count: insight.activityAmount,
          })}
        </p>
      </div>
    </li>
  );
}

function ActivityRow({ activity }: { activity: SpacesActivity }) {
  const { t, i18n } = useTranslation();
  const time = formatCourseMoment(
    activityDate(activity.daysAgo, activity.hour, activity.minute),
    t("spaces.time.yesterdayAt"),
    i18n.resolvedLanguage ?? "zh-CN",
  );
  return (
    <li className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      <p className="text-label text-ink-muted tabular-nums">{time}</p>
      <p className="text-body-dense text-ink-muted min-w-0 break-words">
        {t(`spaces.insights.activity.${activity.kind}`, {
          course: activity.course.name,
          count: activity.amount,
        })}
      </p>
    </li>
  );
}

function activityDate(daysAgo: number, hour: number, minute: number): Date {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  date.setHours(hour, minute, 0, 0);
  return date;
}
