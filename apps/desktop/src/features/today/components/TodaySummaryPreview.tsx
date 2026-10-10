import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { FileText, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { recordApi } from "@/features/records/api/records";
import { recordKeys } from "@/features/records/api/keys";
import type { TodaySummaryTodo } from "@/features/today/api/today";
import { cn } from "@/lib/utils";

export function TodaySummaryPreview({
  record,
  loading,
  error,
  active = true,
}: {
  record?: TodaySummaryTodo;
  loading: boolean;
  error: boolean;
  active?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const summary = useQuery({
    queryKey: recordKeys.summary(record?.record_id ?? ""),
    queryFn: () => recordApi.getSummary(record?.record_id ?? ""),
    enabled: Boolean(record) && active,
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const sample = !record && !loading && !error;
  const content = summary.data?.summary;
  const readyTime = record
    ? new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(record.ready_at))
    : null;
  return (
    <section
      id="today-summary-preview"
      aria-labelledby="today-preview-title"
      tabIndex={-1}
      className="today-panel today-preview w-full p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-preview-title" className="today-heading">
          {t("today.workspace.preview.title")}
        </h2>
        <StatusTag tone={sample ? "neutral" : "warning"}>
          {t(
            sample
              ? "today.stats.insights.sampleTag"
              : "today.workspace.awaiting",
          )}
        </StatusTag>
      </div>
      <h3
        className="mt-3 line-clamp-2 text-xl font-semibold break-words"
        title={record?.title}
      >
        {record?.title ??
          t(
            sample
              ? "today.workspace.preview.sampleTitle"
              : "today.workspace.preview.noSelection",
          )}
      </h3>
      <p className="text-label text-ink-muted mt-1 flex items-start gap-1">
        <FileText className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {record
          ? `${record.course_name} · ${readyTime}`
          : sample
            ? t("today.workspace.preview.sampleSource")
            : t("today.workspace.preview.chooseHint")}
      </p>
      <Tabs defaultValue="preview" className="today-preview-tabs mt-3">
        <TabsList
          variant="line"
          className="border-border-subtle h-auto w-full justify-start border-b p-0"
        >
          <TabsTrigger
            value="preview"
            className="data-active:text-today-accent data-active:after:bg-today-accent flex-none px-3 py-2"
          >
            {t("today.workspace.preview.tab")}
          </TabsTrigger>
          <TabsTrigger value="source" className="flex-none px-3 py-2">
            {t("today.workspace.preview.source")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="preview" className="today-preview-content mt-2">
          {loading || (record && summary.isPending) ? (
            <p role="status" className="text-label text-ink-muted py-4">
              {t("today.loading")}
            </p>
          ) : error || (record && summary.isError) ? (
            <div role="alert" className="py-4">
              <p className="text-label text-destructive">
                {t("today.workspace.preview.error")}
              </p>
              {record ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void summary.refetch()}
                >
                  {t("today.retry")}
                </Button>
              ) : null}
            </div>
          ) : (
            <div
              tabIndex={0}
              role="region"
              aria-label={t("today.workspace.preview.contentLabel")}
              className="today-preview-body text-body-dense max-h-80 overflow-y-auto pr-1 leading-relaxed"
            >
              {sample ? (
                ["difference", "switching", "synchronization"].map(
                  (key, index) => (
                    <div key={key} className="mb-3">
                      <h4 className="font-semibold">
                        {index + 1}.{" "}
                        {t(`today.workspace.preview.sections.${key}.title`)}
                      </h4>
                      <p className="text-ink-muted mt-1">
                        {t(`today.workspace.preview.sections.${key}.body`)}
                      </p>
                    </div>
                  ),
                )
              ) : content ? (
                <>
                  <p className="text-ink-muted mb-3">{content.abstract}</p>
                  {content.sections.map((section, index) => (
                    <div key={`${index}-${section.heading}`} className="mb-3">
                      <h4 className="font-semibold">
                        {index + 1}. {section.heading}
                      </h4>
                      <ul className="text-ink-muted mt-1 list-inside list-disc space-y-1">
                        {section.points.map((point, pointIndex) => (
                          <li key={pointIndex}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              ) : (
                <p className="text-ink-muted py-4">
                  {t("today.workspace.preview.unavailable")}
                </p>
              )}
            </div>
          )}
        </TabsContent>
        <TabsContent
          value="source"
          className="today-preview-content text-label text-ink-muted py-4"
        >
          <p>
            {record
              ? t("today.workspace.preview.sourceHint")
              : t("today.workspace.preview.sampleHint")}
          </p>
          {record ? (
            <Link
              to="/records/$recordId"
              params={{ recordId: record.record_id }}
              search={{ tab: "transcript" }}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mt-3",
              )}
            >
              {t("today.workspace.preview.viewSource")}
            </Link>
          ) : null}
        </TabsContent>
      </Tabs>
      {record ? (
        <div className="today-preview-actions mt-3 grid gap-2">
          <Link
            to="/records/$recordId"
            params={{ recordId: record.record_id }}
            search={{ tab: "transcript" }}
            className="today-preview-source-shortcut bg-today-soft text-label text-ink-muted flex items-center justify-between rounded-sm px-3 py-2"
          >
            <span className="flex items-center gap-2">
              <FileText className="size-4" aria-hidden="true" />
              {t("today.workspace.preview.original")}
            </span>
            <ChevronRight className="size-4" aria-hidden="true" />
          </Link>
          <Link
            to="/records/$recordId"
            params={{ recordId: record.record_id }}
            className={cn(buttonVariants(), "w-full")}
          >
            {t("today.workspace.preview.confirm")}
          </Link>
          <Link
            to="/records/$recordId"
            params={{ recordId: record.record_id }}
            search={{ tab: "transcript" }}
            className={cn(buttonVariants({ variant: "outline" }), "w-full")}
          >
            {t("today.workspace.preview.viewSource")}
          </Link>
          <p className="text-label text-ink-muted text-center">
            {t("today.workspace.preview.confirmHint")}
          </p>
        </div>
      ) : sample ? (
        <div className="today-preview-actions mt-3">
          <Button className="w-full" disabled>
            {t("today.workspace.preview.confirm")}
          </Button>
          <p className="text-label text-ink-muted mt-2 text-center">
            {t("today.workspace.preview.sampleHint")}
          </p>
        </div>
      ) : null}
    </section>
  );
}
