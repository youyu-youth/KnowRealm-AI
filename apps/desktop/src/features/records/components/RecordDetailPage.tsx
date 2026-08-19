import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { ApiError } from "@/services/http/client";

type RecordDetailPageProps = {
  recordId: string;
};

const unavailableTabs = [
  { value: "transcript", labelKey: "record.detail.tabs.transcript" },
  { value: "highlights", labelKey: "record.detail.tabs.highlights" },
  { value: "notes", labelKey: "record.detail.tabs.notes" },
  { value: "flashcards", labelKey: "record.detail.tabs.flashcards" },
  { value: "quiz", labelKey: "record.detail.tabs.quiz" },
] as const;

export function RecordDetailPage({ recordId }: RecordDetailPageProps) {
  const { t } = useTranslation();
  const record = useQuery({
    queryKey: recordKeys.detail(recordId),
    queryFn: () => recordApi.get(recordId),
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404
        ? false
        : failureCount < 2,
  });

  if (record.isPending) {
    return (
      <section className="max-w-workbench px-content mx-auto py-8">
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("record.detail.loading")}
        </p>
      </section>
    );
  }

  if (record.isError) {
    const notFound =
      record.error instanceof ApiError && record.error.status === 404;
    return (
      <section
        role="alert"
        className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col items-start py-8"
      >
        <h1 className="text-headline font-headline text-ink-strong">
          {notFound
            ? t("record.detail.notFoundTitle")
            : t("record.detail.errorTitle")}
        </h1>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {notFound
            ? t("record.detail.notFoundDescription")
            : t("record.detail.errorDescription")}
        </p>
        {notFound ? (
          <Link
            to="/spaces"
            className={buttonVariants({
              variant: "outline",
              className: "mt-8",
            })}
          >
            {t("record.detail.backToSpaces")}
          </Link>
        ) : (
          <Button
            variant="outline"
            className="mt-8"
            onClick={() => void record.refetch()}
          >
            {t("record.detail.retry")}
          </Button>
        )}
      </section>
    );
  }

  const detail = record.data;
  const title = detail.title.trim() || t("spaces.records.untitled");
  const backLinkClass =
    "text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex items-center gap-1.5 rounded-sm transition-colors focus-visible:ring-3";

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full min-w-0 flex-col py-8">
      {detail.course_id ? (
        <Link
          to="/spaces/$courseId"
          params={{ courseId: detail.course_id }}
          search={{ tab: "records" }}
          className={backLinkClass}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t("record.detail.backToCourseRecords")}
        </Link>
      ) : (
        <Link to="/spaces" className={backLinkClass}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t("record.detail.backToSpaces")}
        </Link>
      )}

      <header className="mt-5 min-w-0">
        <h1
          className="text-headline font-headline text-ink-strong truncate"
          title={title}
        >
          {title}
        </h1>
        <div className="text-label text-muted-foreground mt-3 flex flex-wrap items-center gap-x-2 gap-y-2">
          <span>{t(captureTypeLabelKeys[detail.capture_type])}</span>
          <span aria-hidden="true">·</span>
          <time dateTime={detail.created_at}>
            {t("spaces.records.createdAt", {
              date: recordDateFormatter.format(new Date(detail.created_at)),
            })}
          </time>
          {detail.duration_ms > 0 ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{formatRecordDuration(detail.duration_ms, t)}</span>
            </>
          ) : null}
          <span
            className={`${statusClassNames[detail.status]} font-label rounded-xs px-2 py-1 whitespace-nowrap`}
          >
            {t(statusLabelKeys[detail.status])}
          </span>
        </div>
      </header>

      <Tabs value="summary" className="mt-8 min-w-0">
        <TabsList
          variant="line"
          className="max-w-full flex-wrap justify-start gap-x-3 gap-y-2"
        >
          <TabsTrigger value="summary">
            {t("record.detail.tabs.summary")}
          </TabsTrigger>
          {unavailableTabs.map(({ value, labelKey }) => (
            <TabsTrigger
              key={value}
              value={value}
              disabled
              aria-describedby="record-assets-unavailable"
              className="aria-disabled:hover:text-foreground/60 aria-disabled:pointer-events-auto"
            >
              {t(labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        <p
          id="record-assets-unavailable"
          className="text-label text-muted-foreground mt-3"
        >
          {t("record.detail.assetsUnavailable")}
        </p>
        <TabsContent
          value="summary"
          className="border-border mt-6 border-t pt-8"
        >
          <h2 className="text-section font-section text-ink">
            {detail.status === "FAILED"
              ? t("record.detail.failedTitle")
              : t("record.detail.summaryEmptyTitle")}
          </h2>
          <p className="max-w-reading text-body text-muted-foreground mt-2">
            {detail.status === "FAILED"
              ? t("record.detail.failedDescription")
              : t("record.detail.summaryEmptyDescription")}
          </p>
        </TabsContent>
      </Tabs>
    </section>
  );
}
