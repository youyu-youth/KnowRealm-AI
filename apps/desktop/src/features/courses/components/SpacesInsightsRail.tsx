import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpenText,
  CalendarClock,
  FileText,
  Layers3,
  Mic,
  StickyNote,
} from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
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
  type SpacesPendingItemKey,
} from "@/features/courses/spacesInsights";

const statItems = [
  {
    key: "courseCount",
    icon: BookOpenText,
    iconClass:
      "bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-300",
  },
  {
    key: "knowledgePointCount",
    icon: Layers3,
    iconClass:
      "bg-violet-50 text-violet-600 dark:bg-violet-950/50 dark:text-violet-300",
  },
  {
    key: "recordCount",
    icon: FileText,
    iconClass:
      "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  {
    key: "activeThisWeek",
    icon: CalendarClock,
    iconClass:
      "bg-orange-50 text-orange-600 dark:bg-orange-950/50 dark:text-orange-300",
  },
] as const;

const pendingIcons = {
  notes: StickyNote,
  knowledgePoints: Layers3,
  documents: FileText,
  recordings: Mic,
} satisfies Record<SpacesPendingItemKey, typeof StickyNote>;

type SpacesInsightsRailProps = {
  courses: Course[];
};

export function SpacesInsightsRail({ courses }: SpacesInsightsRailProps) {
  const { t } = useTranslation();
  const overview = mockSpacesOverview(courses);
  const recent = mockRecentCourses(courses, 4);
  const activities = mockActivities(courses, 5);

  return (
    <div className="grid gap-4">
      <InsightsCard title={t("spaces.insights.stats.title")}>
        <dl className="mt-3.5 grid grid-cols-2 gap-x-3 gap-y-3.5">
          {statItems.map(({ key, icon: Icon, iconClass }) => (
            <div key={key} className="flex min-w-0 items-center gap-2.5">
              <span
                className={`${iconClass} flex size-8 shrink-0 items-center justify-center rounded-lg`}
              >
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <dd className="text-section font-section text-ink-strong tabular-nums">
                  {overview[key]}
                </dd>
                <dt className="text-label text-ink-muted truncate">
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

      <InsightsCard
        title={t("spaces.insights.pending.title")}
        action={
          <Link
            to="/inbox"
            className="text-label text-ink-muted hover:text-ink-strong inline-flex items-center gap-1"
          >
            {t("spaces.insights.viewAll")}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        }
      >
        <ul className="mt-3 grid gap-2.5">
          {mockPendingItems.map((item) => {
            const Icon = pendingIcons[item.key];
            return (
              <li key={item.key} className="flex min-w-0 items-center gap-2.5">
                <span className="border-border-subtle bg-surface-subtle text-ink-muted flex size-8 shrink-0 items-center justify-center rounded-lg border">
                  <Icon className="size-4" aria-hidden="true" />
                </span>
                <span className="text-body-dense text-ink-muted min-w-0 flex-1 truncate">
                  {t(`spaces.insights.pending.${item.key}`)}
                </span>
                <span className="text-body-dense text-ink-strong shrink-0 font-medium tabular-nums">
                  {item.count}
                </span>
              </li>
            );
          })}
        </ul>
      </InsightsCard>

      <InsightsCard title={t("spaces.insights.activity.title")}>
        {activities.length > 0 ? (
          <ol className="border-border-subtle mt-3.5 grid gap-3.5 border-l pl-4">
            {activities.map((activity) => (
              <ActivityRow key={activity.id} activity={activity} />
            ))}
          </ol>
        ) : (
          <p className="text-label text-ink-muted mt-3">
            {t("spaces.insights.activity.empty")}
          </p>
        )}
      </InsightsCard>
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
    <li className="relative">
      <span
        aria-hidden="true"
        className="bg-border-strong absolute top-1.5 -left-[calc(1rem+3px)] size-1.5 rounded-full"
      />
      <p className="text-label text-ink-muted tabular-nums">{time}</p>
      <p className="text-body-dense text-ink-muted mt-0.5">
        {t(`spaces.insights.activity.${activity.kind}`, {
          course: activity.course.name,
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
