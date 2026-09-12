import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { CourseRecordRow } from "@/features/courses/components/CourseRecordRow";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";

type CourseRecordsPanelProps = {
  courseId: string;
};

export function CourseRecordsPanel({ courseId }: CourseRecordsPanelProps) {
  const { t } = useTranslation();
  const records = useQuery({
    queryKey: recordKeys.courseList(courseId),
    queryFn: () => recordApi.listForCourse(courseId),
  });

  if (records.isPending) {
    return (
      <SurfaceCard title={t("spaces.records.title")}>
        <p
          role="status"
          className="text-body text-muted-foreground mt-4 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.records.loading")}
        </p>
      </SurfaceCard>
    );
  }

  if (records.isError) {
    return (
      <SurfaceCard title={t("spaces.records.title")}>
        <div role="alert" className="mt-4">
          <h3 className="text-section font-section text-ink">
            {t("spaces.records.errorTitle")}
          </h3>
          <p className="max-w-reading text-body text-muted-foreground mt-2">
            {t("spaces.records.errorDescription")}
          </p>
          <Button
            variant="outline"
            className="mt-5"
            onClick={() => void records.refetch()}
          >
            {t("spaces.records.retry")}
          </Button>
        </div>
      </SurfaceCard>
    );
  }

  if (records.data.length === 0) {
    return (
      <SurfaceCard title={t("spaces.records.title")}>
        <Empty className="items-start rounded-none p-0 pt-8 text-start">
          <EmptyHeader className="items-start text-start">
            <h3 className="text-section font-section text-ink">
              {t("spaces.records.emptyTitle")}
            </h3>
            <EmptyDescription className="max-w-reading text-body">
              {t("spaces.records.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </SurfaceCard>
    );
  }

  return (
    <SurfaceCard title={t("spaces.records.title")}>
      <ul
        aria-label={t("spaces.records.listLabel")}
        className="mt-3 flex flex-col gap-1"
      >
        {records.data.map((record) => (
          <li key={record.id} className="min-w-0">
            <CourseRecordRow record={record} />
          </li>
        ))}
      </ul>
    </SurfaceCard>
  );
}
