import {
  Briefcase,
  Clock,
  FileText,
  GraduationCap,
  Layers3,
  Lightbulb,
  MoreHorizontal,
  Pencil,
  Trash2,
  FolderOpen,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Course, LearningContext } from "@/features/courses/api/types";
import { courseStatusLabelKeys } from "@/features/courses/courseOptions";
import { CourseMetaTags } from "@/features/courses/components/CourseMetaTags";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";
import { CourseCover } from "@/features/courses/components/CourseCover";
import { mockCourseStats } from "@/features/courses/spacesInsights";

const contextAvatarClassNames = {
  SCHOOL: "bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-300",
  CAREER:
    "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300",
  INTEREST:
    "bg-violet-50 text-violet-600 dark:bg-violet-950/50 dark:text-violet-300",
} satisfies Record<LearningContext, string>;

const contextIcons = {
  SCHOOL: GraduationCap,
  CAREER: Briefcase,
  INTEREST: Lightbulb,
} satisfies Record<LearningContext, typeof GraduationCap>;

const activeStatusClassName =
  "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/45 dark:text-emerald-300";
const archivedStatusClassName =
  "bg-surface-subtle text-muted-foreground dark:bg-surface-strong";

export function CourseAvatar({
  context,
  size = "md",
}: {
  context: LearningContext;
  size?: "md" | "sm";
}) {
  const Icon = contextIcons[context];
  return (
    <span
      aria-hidden="true"
      className={`${contextAvatarClassNames[context]} ${size === "md" ? "size-10 rounded-lg" : "size-8 rounded-md"} flex shrink-0 items-center justify-center`}
    >
      <Icon className={size === "md" ? "size-5" : "size-4"} />
    </span>
  );
}

export function CourseStatusTag({ course }: { course: Course }) {
  const { t } = useTranslation();
  return (
    <span
      className={`text-label font-label inline-flex h-5 items-center rounded-sm px-1.5 whitespace-nowrap ${course.status === "ACTIVE" ? activeStatusClassName : archivedStatusClassName}`}
    >
      {t(courseStatusLabelKeys[course.status])}
    </span>
  );
}

type CourseCardProps = {
  course: Course;
  onOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
};

export function CourseCard({
  course,
  onOpen,
  onEdit,
  onDelete,
}: CourseCardProps) {
  const { t, i18n } = useTranslation();
  const stats = mockCourseStats(course.id);
  const updatedAt = formatCourseMoment(
    course.updated_at,
    t("spaces.time.yesterdayAt"),
    i18n.resolvedLanguage ?? "zh-CN",
  );
  const description =
    course.description?.trim() || t("spaces.card.noDescription");

  return (
    <article className="spaces-course-card group">
      <CourseCover course={course} />
      <div className="flex min-w-0 items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onOpen}
              className="text-body text-ink-strong focus-visible:ring-ring/40 min-w-0 text-left font-semibold break-words focus-visible:rounded-sm focus-visible:ring-3 focus-visible:outline-hidden"
              aria-label={t("spaces.card.open", { name: course.name })}
              title={course.name}
            >
              {course.name}
            </button>
            <CourseStatusTag course={course} />
          </div>
          <div className="mt-1">
            <CourseMetaTags course={course} />
          </div>
        </div>
      </div>

      <p className="text-body-dense text-ink-muted mt-1 line-clamp-2">
        {description}
      </p>

      <div className="spaces-card-summary mt-2">
        <dl
          className="grid flex-1 grid-cols-3 gap-2"
          aria-label={t("spaces.card.sampleStats")}
        >
          <div className="min-w-0">
            <dt className="text-label text-ink-muted flex items-center gap-1">
              <FileText className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate">{t("spaces.card.records")}</span>
            </dt>
            <dd className="text-body-dense text-ink-strong mt-0.5 font-semibold tabular-nums">
              {t("spaces.card.recordsValue", { count: stats.records })}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-label text-ink-muted flex items-center gap-1">
              <Layers3 className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate">
                {t("spaces.card.knowledgePoints")}
              </span>
            </dt>
            <dd className="text-body-dense text-ink-strong mt-0.5 font-semibold tabular-nums">
              {t("spaces.card.knowledgePointsValue", {
                count: stats.knowledgePoints,
              })}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-label text-ink-muted flex items-center gap-1">
              <Clock className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate">{t("spaces.card.updatedAt")}</span>
            </dt>
            <dd
              className="text-body-dense text-ink-strong mt-0.5 font-semibold"
              title={course.updated_at}
            >
              <time dateTime={course.updated_at}>{updatedAt}</time>
            </dd>
          </div>
        </dl>

        <div className="spaces-card-progress">
          <div className="text-label flex flex-wrap items-center justify-between gap-1">
            <span
              className="text-ink-muted font-label"
              title={t("spaces.card.sampleStats")}
            >
              {t("spaces.insights.sample")}
            </span>
            <span className="text-ink-strong font-label tabular-nums">
              {t("spaces.card.progressValue", { percent: stats.progress })}
            </span>
          </div>
          <div
            role="progressbar"
            aria-label={t("spaces.card.progress")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={stats.progress}
            className="bg-surface-strong mt-1 h-1.5 w-full overflow-hidden rounded-full"
          >
            <div
              className="bg-spaces-accent h-full rounded-full"
              style={{ width: `${stats.progress}%` }}
            />
          </div>
        </div>
      </div>
      <div className="mt-auto flex items-center gap-2 pt-2">
        <Button size="sm" className="flex-1" onClick={onOpen}>
          <FolderOpen data-icon="inline-start" aria-hidden="true" />
          {t("spaces.card.openAction")}
        </Button>
        <Button size="sm" variant="outline" className="flex-1" onClick={onEdit}>
          <Pencil data-icon="inline-start" aria-hidden="true" />
          {t("spaces.card.editAction")}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                size="icon-sm"
                variant="outline"
                aria-label={t("spaces.card.moreActions", { name: course.name })}
              />
            }
          >
            <MoreHorizontal aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-40">
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 aria-hidden="true" />
              {t("spaces.delete.action")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </article>
  );
}
