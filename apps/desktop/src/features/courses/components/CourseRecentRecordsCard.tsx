import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { CourseRecordRow } from "@/features/courses/components/CourseRecordRow";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";

/** 最近学习记录：真实记录取最近 5 条，「查看全部」跳学习记录标签页。 */
export function CourseRecentRecordsCard({
  courseId,
  onViewAll,
}: {
  courseId: string;
  onViewAll: () => void;
}) {
  const { t } = useTranslation();
  const records = useQuery({
    queryKey: recordKeys.courseList(courseId),
    queryFn: () => recordApi.listForCourse(courseId),
  });
  const recent = [...(records.data ?? [])]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 5);

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.recentRecords.title")}
      action={
        records.data && records.data.length > 0 ? (
          <Button variant="ghost" size="sm" onClick={onViewAll}>
            {t("spaces.insights.viewAll")}
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        ) : undefined
      }
    >
      {records.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-3 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.records.loading")}
        </p>
      ) : records.isError ? (
        <p className="text-body-dense text-ink-muted mt-3">
          {t("spaces.courseDetail.recentRecords.unavailable")}
        </p>
      ) : recent.length === 0 ? (
        <p className="text-body-dense text-ink-muted mt-3">
          {t("spaces.records.emptyTitle")}
        </p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1">
          {recent.map((record) => (
            <li key={record.id} className="min-w-0">
              <CourseRecordRow record={record} variant="compact" />
            </li>
          ))}
        </ul>
      )}
    </SurfaceCard>
  );
}
