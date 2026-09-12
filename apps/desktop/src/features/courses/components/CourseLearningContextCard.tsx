import {
  CalendarClock,
  GraduationCap,
  Layers3,
  Target,
  TrendingUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  educationStageLabelKeys,
  learningContextLabelKeys,
  learningDepthLabelKeys,
} from "@/features/courses/courseOptions";
import {
  mockCurrentProgress,
  mockLearningGoalKey,
} from "@/features/courses/courseDetailInsights";

/** 学习上下文：场景/阶段/深度为真实字段，当前进度与学习目标为示意。 */
export function CourseLearningContextCard({
  course,
}: {
  course: CourseDetail;
}) {
  const { t } = useTranslation();
  const progress = mockCurrentProgress(course);
  const rows: Array<{
    key: string;
    icon: typeof GraduationCap;
    label: string;
    value: string;
    sample?: boolean;
  }> = [
    {
      key: "context",
      icon: GraduationCap,
      label: t("spaces.detail.label.context"),
      value: t(learningContextLabelKeys[course.learning_context]),
    },
    {
      key: "stage",
      icon: CalendarClock,
      label: t("spaces.detail.label.educationStage"),
      value: course.education_stage
        ? t(educationStageLabelKeys[course.education_stage])
        : t("spaces.detail.notSetValue"),
    },
    {
      key: "depth",
      icon: Layers3,
      label: t("spaces.detail.label.depth"),
      value: course.depth
        ? t(learningDepthLabelKeys[course.depth])
        : t("spaces.detail.notSetValue"),
    },
    {
      key: "progress",
      icon: TrendingUp,
      label: t("spaces.courseDetail.context.currentProgress"),
      value: t("spaces.courseDetail.context.currentProgressValue", {
        chapter: progress.index,
        name: t(progress.nameKey),
      }),
      sample: true,
    },
    {
      key: "goal",
      icon: Target,
      label: t("spaces.courseDetail.context.goal"),
      value: t(mockLearningGoalKey(course)),
      sample: true,
    },
  ];

  return (
    <SurfaceCard title={t("spaces.courseDetail.context.title")}>
      <dl className="mt-3 flex flex-col">
        {rows.map(({ key, icon: Icon, label, value, sample }) => (
          <div
            key={key}
            className="border-border-subtle flex min-w-0 items-start gap-2.5 border-b py-2.5 last:border-b-0"
          >
            <Icon
              className="text-ink-faint mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <dt className="text-label text-ink-muted w-16 shrink-0 pt-0.5">
              {label}
            </dt>
            <dd className="text-body-dense text-ink min-w-0 flex-1 break-words">
              {value}
              {sample ? (
                <span className="text-label text-ink-faint ml-1.5">
                  {t("spaces.insights.sample")}
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </SurfaceCard>
  );
}
