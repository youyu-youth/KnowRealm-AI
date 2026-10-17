import { Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  courseDateFormatter,
  courseTypeLabelKeys,
  educationStageLabelKeys,
  learningContextLabelKeys,
  learningDepthLabelKeys,
} from "@/features/courses/courseOptions";
import { mockSubjectKey } from "@/features/courses/courseDetailInsights";
import { CourseStatusTag } from "@/features/courses/components/CourseCard";
import { captureTypeLabelKeys } from "@/features/records/recordPresentation";
import type { RecordOut } from "@/features/records/api/types";

type CourseInfoPanelProps = {
  course: CourseDetail;
  records: RecordOut[];
  onEdit: () => void;
};

/** 课程信息面板：真实字段为主，所属学科为示意。结构列形态，通过发丝线与主内容分隔，不做卡片壳。 */
export function CourseInfoPanel({
  course,
  records,
  onEdit,
}: CourseInfoPanelProps) {
  const { t } = useTranslation();
  const resourceKeys = Array.from(
    new Set(records.map((record) => record.capture_type)),
  ).slice(0, 4);

  return (
    <section className="flex min-w-0 flex-col">
      <header className="flex min-w-0 items-center justify-between gap-3">
        <h2 className="text-section font-section text-ink-strong truncate">
          {t("spaces.detail.infoTitle")}
        </h2>
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Pencil data-icon="inline-start" aria-hidden="true" />
          {t("spaces.detail.edit")}
        </Button>
      </header>

      <dl className="mt-2 flex flex-col">
        <InfoRow label={t("spaces.detail.label.name")} value={course.name} />
        <InfoRow
          label={t("spaces.detail.label.courseType")}
          value={
            course.course_type
              ? t(courseTypeLabelKeys[course.course_type])
              : t("spaces.detail.notSetValue")
          }
        />
        <InfoRow
          label={t("spaces.courseDetail.info.subject")}
          value={t(mockSubjectKey(course))}
          sample
        />
        <InfoRow
          label={t("spaces.detail.label.educationStage")}
          value={
            course.education_stage
              ? t(educationStageLabelKeys[course.education_stage])
              : t("spaces.detail.notSetValue")
          }
        />
        <InfoRow
          label={t("spaces.detail.label.depth")}
          value={
            course.depth
              ? t(learningDepthLabelKeys[course.depth])
              : t("spaces.detail.notSetValue")
          }
        />
        <InfoRow
          label={t("spaces.detail.label.context")}
          value={t(learningContextLabelKeys[course.learning_context])}
        />
        <div className="border-border-subtle flex min-w-0 items-start gap-3 border-b py-2.5 last:border-b-0">
          <dt className="text-label text-ink-muted w-20 shrink-0 pt-0.5">
            {t("spaces.courseDetail.info.status")}
          </dt>
          <dd className="min-w-0 flex-1">
            <CourseStatusTag course={course} />
            <span className="text-label text-ink-faint ml-1.5">
              ({course.status})
            </span>
          </dd>
        </div>
        <InfoRow
          label={t("spaces.courseDetail.info.createdAt")}
          value={courseDateFormatter.format(new Date(course.created_at))}
        />
        <InfoRow
          label={t("spaces.courseDetail.info.recentLearning")}
          value={courseDateFormatter.format(new Date(course.updated_at))}
          title={course.updated_at}
        />
        <InfoRow
          label={t("spaces.courseDetail.info.resources")}
          value={
            resourceKeys.length > 0
              ? resourceKeys
                  .map((key) => t(captureTypeLabelKeys[key]))
                  .join(" · ")
              : t("spaces.detail.notSetValue")
          }
        />
      </dl>
    </section>
  );
}

function InfoRow({
  label,
  value,
  sample = false,
  title,
}: {
  label: string;
  value: string;
  sample?: boolean;
  title?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="border-border-subtle flex min-w-0 items-start gap-3 border-b py-2.5 last:border-b-0">
      <dt className="text-label text-ink-muted w-20 shrink-0 pt-0.5">
        {label}
      </dt>
      <dd className="text-body-dense text-ink min-w-0 flex-1 break-words">
        <span title={title}>{value}</span>
        {sample ? (
          <span className="text-label text-ink-faint ml-1.5">
            {t("spaces.insights.sample")}
          </span>
        ) : null}
      </dd>
    </div>
  );
}
