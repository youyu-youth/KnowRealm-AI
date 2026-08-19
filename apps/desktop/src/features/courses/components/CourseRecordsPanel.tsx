import { useQuery } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { CaptureType, RecordStatus } from "@/features/records/api/types";

type CourseRecordsPanelProps = {
  courseId: string;
};

const captureTypeLabelKeys = {
  RECORDING: "spaces.records.captureType.RECORDING",
  AUDIO_IMPORT: "spaces.records.captureType.AUDIO_IMPORT",
  DOCUMENT_IMPORT: "spaces.records.captureType.DOCUMENT_IMPORT",
  PASTE: "spaces.records.captureType.PASTE",
  QUICK_NOTE: "spaces.records.captureType.QUICK_NOTE",
  CLIP: "spaces.records.captureType.CLIP",
} satisfies Record<CaptureType, string>;

const statusLabelKeys = {
  NOTE: "spaces.records.status.NOTE",
  DRAFT: "spaces.records.status.DRAFT",
  CONTENT_PROCESSING: "spaces.records.status.CONTENT_PROCESSING",
  SUMMARY_PENDING: "spaces.records.status.SUMMARY_PENDING",
  SUMMARY_PROCESSING: "spaces.records.status.SUMMARY_PROCESSING",
  SUMMARY_READY: "spaces.records.status.SUMMARY_READY",
  COMPLETED: "spaces.records.status.COMPLETED",
  FAILED: "spaces.records.status.FAILED",
} satisfies Record<RecordStatus, string>;

const statusClassNames = {
  NOTE: "bg-surface-subtle text-muted-foreground",
  DRAFT: "bg-surface-subtle text-muted-foreground",
  CONTENT_PROCESSING: "bg-learning-soft text-learning",
  SUMMARY_PENDING: "bg-learning-soft text-learning",
  SUMMARY_PROCESSING: "bg-learning-soft text-learning",
  SUMMARY_READY: "bg-learning-soft text-learning",
  COMPLETED: "bg-surface-subtle text-ink",
  FAILED: "bg-destructive/10 text-destructive",
} satisfies Record<RecordStatus, string>;

const recordDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatDuration(durationMs: number, t: TFunction): string {
  const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [
    hours ? t("spaces.records.duration.hours", { count: hours }) : null,
    minutes ? t("spaces.records.duration.minutes", { count: minutes }) : null,
    seconds ? t("spaces.records.duration.seconds", { count: seconds }) : null,
  ]
    .filter(Boolean)
    .join(" ");
}

export function CourseRecordsPanel({ courseId }: CourseRecordsPanelProps) {
  const { t } = useTranslation();
  const records = useQuery({
    queryKey: recordKeys.courseList(courseId),
    queryFn: () => recordApi.listForCourse(courseId),
  });

  if (records.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2 border-t pt-8"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.records.loading")}
      </p>
    );
  }

  if (records.isError) {
    return (
      <section role="alert" className="border-border border-t pt-8">
        <h2 className="text-section font-section text-ink">
          {t("spaces.records.errorTitle")}
        </h2>
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
      </section>
    );
  }

  if (records.data.length === 0) {
    return (
      <Empty className="border-border items-start rounded-none border-t p-0 pt-8 text-start">
        <EmptyHeader className="items-start text-start">
          <h2 className="text-section font-section text-ink">
            {t("spaces.records.emptyTitle")}
          </h2>
          <EmptyDescription className="max-w-reading text-body">
            {t("spaces.records.emptyDescription")}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <section className="border-border border-t pt-8">
      <h2 className="text-section font-section text-ink">
        {t("spaces.records.title")}
      </h2>
      <ul aria-label={t("spaces.records.listLabel")} className="mt-3">
        {records.data.map((record) => {
          const title = record.title.trim() || t("spaces.records.untitled");
          return (
            <li
              key={record.id}
              className="border-border grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b py-4 last:border-b-0"
            >
              <div className="min-w-0">
                <h3
                  className="text-body font-section text-ink truncate"
                  title={title}
                >
                  {title}
                </h3>
                <div className="text-label text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span>{t(captureTypeLabelKeys[record.capture_type])}</span>
                  <span aria-hidden="true">·</span>
                  <time dateTime={record.created_at}>
                    {t("spaces.records.createdAt", {
                      date: recordDateFormatter.format(
                        new Date(record.created_at),
                      ),
                    })}
                  </time>
                  {record.duration_ms > 0 ? (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>{formatDuration(record.duration_ms, t)}</span>
                    </>
                  ) : null}
                </div>
              </div>
              <span
                className={`${statusClassNames[record.status]} text-label font-label rounded-xs px-2 py-1 whitespace-nowrap`}
              >
                {t(statusLabelKeys[record.status])}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
