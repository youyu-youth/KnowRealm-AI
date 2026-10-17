import { Archive, ArchiveRestore, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";

type CourseSidebarActionsProps = {
  course: CourseDetail;
  onEdit: () => void;
  onDelete: () => void;
  onArchive: () => void;
  onRestore: () => void;
  restorePending: boolean;
};

const MAX_VISIBLE_TAGS = 4;

export function CourseSidebarActions({
  course,
  onEdit,
  onDelete,
  onArchive,
  onRestore,
  restorePending,
}: CourseSidebarActionsProps) {
  const { t } = useTranslation();
  const hotWords = course.hot_words ?? [];

  return (
    <section className="course-sidebar-actions min-w-0">
      <div className="border-border-subtle mt-3 flex min-w-0 flex-wrap items-center gap-1.5 border-t pt-3">
        <span className="text-label text-ink-muted w-20 shrink-0">
          {t("spaces.detail.label.hotWords")}
        </span>
        {hotWords.length === 0 ? (
          <span className="text-label text-ink-faint">
            {t("spaces.detail.noHotWords")}
          </span>
        ) : (
          hotWords.slice(0, MAX_VISIBLE_TAGS).map((word) => (
            <span
              key={word}
              className="bg-surface-subtle text-ink-neutral text-label font-label inline-flex h-6 items-center rounded-sm px-2 whitespace-nowrap"
            >
              {word}
            </span>
          ))
        )}
        {hotWords.length > MAX_VISIBLE_TAGS ? (
          <span className="text-label text-ink-faint">
            +{hotWords.length - MAX_VISIBLE_TAGS}
          </span>
        ) : null}
        <button
          type="button"
          onClick={onEdit}
          aria-label={t("spaces.courseDetail.info.addTag")}
          className="border-border-strong text-ink-muted hover:bg-surface-subtle focus-visible:ring-ring/40 inline-flex size-6 items-center justify-center rounded-sm border transition-colors focus-visible:ring-3"
        >
          <Plus className="size-3.5" aria-hidden="true" />
        </button>
      </div>

      <div className="border-border-subtle mt-3 border-t pt-3">
        <Button
          variant="ghost"
          size="sm"
          className="justify-start"
          disabled={restorePending}
          onClick={course.status === "ARCHIVED" ? onRestore : onArchive}
        >
          {course.status === "ARCHIVED" ? (
            <>
              <ArchiveRestore data-icon="inline-start" aria-hidden="true" />
              {t("spaces.archive.restoreAction")}
            </>
          ) : (
            <>
              <Archive data-icon="inline-start" aria-hidden="true" />
              {t("spaces.archive.action")}
            </>
          )}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:bg-danger-soft dark:hover:bg-danger-soft justify-start"
          onClick={onDelete}
        >
          <Trash2 data-icon="inline-start" aria-hidden="true" />
          {t("spaces.delete.action")}
        </Button>
      </div>
    </section>
  );
}
