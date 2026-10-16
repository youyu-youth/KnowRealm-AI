import { useQuery } from "@tanstack/react-query";
import { ArrowRight, MoreVertical } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
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
  const navigate = useNavigate();
  const records = useQuery({
    queryKey: recordKeys.courseList(courseId),
    queryFn: () => recordApi.listForCourse(courseId),
  });
  const recent = [...(records.data ?? [])]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 5);

  return (
    <SurfaceCard
      className="course-overview-section course-recent-records"
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
        <div className="mt-3 flex flex-col items-start gap-2">
          <p role="alert" className="text-body-dense text-ink-muted">
            {t("spaces.courseDetail.recentRecords.unavailable")}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void records.refetch()}
          >
            {t("spaces.detail.retry")}
          </Button>
        </div>
      ) : recent.length === 0 ? (
        <p className="text-body-dense text-ink-muted mt-3">
          {t("spaces.records.emptyTitle")}
        </p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1">
          {recent.map((record) => (
            <li key={record.id} className="flex min-w-0 items-center">
              <div className="min-w-0 flex-1">
                <CourseRecordRow record={record} variant="compact" />
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t(
                        "spaces.courseDetail.recentRecords.actions",
                        {
                          title:
                            record.title.trim() || t("spaces.records.untitled"),
                        },
                      )}
                    />
                  }
                >
                  <MoreVertical aria-hidden="true" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() =>
                      void navigate({
                        to: "/records/$recordId",
                        params: { recordId: record.id },
                      })
                    }
                  >
                    {t("spaces.courseDetail.recentRecords.open")}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onViewAll}>
                    {t("spaces.insights.viewAll")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          ))}
        </ul>
      )}
    </SurfaceCard>
  );
}
