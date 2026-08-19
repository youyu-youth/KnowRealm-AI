import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  courseLevelLabelKey,
  courseTypeLabelKeys,
  learningContextLabelKeys,
} from "@/features/courses/courseOptions";
import { EditCourseForm } from "@/features/courses/components/EditCourseForm";
import { DeleteCourseDialog } from "@/features/courses/components/DeleteCourseDialog";

type CourseOverviewProps = {
  course: CourseDetail;
  onDeleted: () => void | Promise<void>;
};

export function CourseOverview({ course, onDeleted }: CourseOverviewProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <EditCourseForm
        course={course}
        onCancel={() => setEditing(false)}
        onSaved={() => setEditing(false)}
      />
    );
  }

  const levelKey = courseLevelLabelKey(course);
  const hotWords = course.hot_words ?? [];
  const rows: Array<{ label: string; value: string | null }> = [
    { label: t("spaces.detail.label.name"), value: course.name },
    {
      label: t("spaces.detail.label.context"),
      value: t(learningContextLabelKeys[course.learning_context]),
    },
    {
      label:
        course.learning_context === "SCHOOL"
          ? t("spaces.detail.label.educationStage")
          : t("spaces.detail.label.depth"),
      value: levelKey ? t(levelKey) : null,
    },
    {
      label: t("spaces.detail.label.courseType"),
      value: course.course_type
        ? t(courseTypeLabelKeys[course.course_type])
        : t("spaces.detail.notSetValue"),
    },
    {
      label: t("spaces.detail.label.description"),
      value: course.description ?? t("spaces.detail.noDescription"),
    },
    {
      label: t("spaces.detail.label.hotWords"),
      value:
        hotWords.length > 0
          ? hotWords.join(" · ")
          : t("spaces.detail.noHotWords"),
    },
  ];

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-6">
        <h2 className="text-section font-section text-ink">
          {t("spaces.detail.infoTitle")}
        </h2>
        <div className="flex items-center gap-2">
          <DeleteCourseDialog course={course} onDeleted={onDeleted} />
          <Button onClick={() => setEditing(true)}>
            {t("spaces.detail.edit")}
          </Button>
        </div>
      </div>
      <dl className="border-border mt-4 border-t">
        {rows.map((row) => (
          <div
            key={row.label}
            className="border-border max-compact:grid-cols-[128px_minmax(0,1fr)] grid grid-cols-[180px_minmax(0,1fr)] gap-6 border-b py-3"
          >
            <dt className="text-label text-muted-foreground pt-0.5">
              {row.label}
            </dt>
            <dd className="text-body text-ink min-w-0 break-words whitespace-pre-wrap">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
