import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  ClipboardPaste,
  FilePlus2,
  FileText,
  FolderOpen,
  Inbox,
  Layers3,
  ListTodo,
  Mic2,
  PencilLine,
  Rocket,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import { InboxRowActions } from "@/features/inbox/InboxRowActions";
import {
  isInboxTypeFilter,
  type InboxSearch,
  type InboxStatusFilter,
  type InboxTypeFilter,
} from "@/features/inbox/inboxSearch";
import { formatSize } from "@/lib/utils";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type {
  CaptureType,
  InboxRecordOut,
  RecordOut,
} from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusLabelKeys,
} from "@/features/records/recordPresentation";

const PAGE_SIZE = 20;
const ORGANIZABLE_STATUSES = new Set(["NOTE", "SUMMARY_PENDING"]);
const PROCESSING_STATUSES = new Set([
  "DRAFT",
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

const inboxStatusClassNames = {
  NOTE: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/45 dark:text-emerald-300",
  DRAFT: "bg-surface-subtle text-muted-foreground",
  CONTENT_PROCESSING:
    "bg-blue-50 text-blue-700 dark:bg-blue-950/45 dark:text-blue-300",
  SUMMARY_PENDING:
    "bg-amber-50 text-amber-700 dark:bg-amber-950/45 dark:text-amber-300",
  SUMMARY_PROCESSING:
    "bg-blue-50 text-blue-700 dark:bg-blue-950/45 dark:text-blue-300",
  SUMMARY_READY:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/45 dark:text-emerald-300",
  COMPLETED: "bg-surface-subtle text-ink",
  FAILED: "bg-red-50 text-red-700 dark:bg-red-950/45 dark:text-red-300",
} satisfies Record<RecordOut["status"], string>;

const listTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const typeFilters = [
  "all",
  "quick-note",
  "paste",
  "audio",
  "document",
  "other",
] as const;

const statusFilters = [
  "unfiled",
  "upgradable",
  "processing",
  "failed",
] as const;

function inboxMetaText(record: InboxRecordOut, t: TFunction): string {
  const parts: string[] = [];
  const isAudio = ["RECORDING", "AUDIO_IMPORT"].includes(record.capture_type);
  const isText = ["QUICK_NOTE", "PASTE"].includes(record.capture_type);
  if (isAudio && record.duration_ms > 0) {
    parts.push(
      t("inbox.meta.duration", {
        duration: formatRecordDuration(record.duration_ms, t),
      }),
    );
  }
  if (!isText) {
    const size = formatSize(record.file_size_bytes ?? null);
    if (size) parts.push(size);
  }
  if (
    !isAudio &&
    (isText ||
      record.capture_type === "MULTI_SOURCE" ||
      record.capture_type === "CLIP") &&
    record.content_chars != null
  ) {
    parts.push(t("inbox.meta.characters", { count: record.content_chars }));
  }
  return parts.join(" · ");
}

function matchesType(record: RecordOut, filter: InboxTypeFilter) {
  if (filter === "all") return true;
  if (filter === "quick-note") return record.capture_type === "QUICK_NOTE";
  if (filter === "paste") return record.capture_type === "PASTE";
  if (filter === "audio")
    return ["RECORDING", "AUDIO_IMPORT"].includes(record.capture_type);
  if (filter === "document") return record.capture_type === "DOCUMENT_IMPORT";
  return ["MULTI_SOURCE", "CLIP"].includes(record.capture_type);
}

function matchesStatus(record: RecordOut, filter: InboxStatusFilter) {
  if (filter === "unfiled") return true;
  if (filter === "upgradable") return ORGANIZABLE_STATUSES.has(record.status);
  if (filter === "processing") return PROCESSING_STATUSES.has(record.status);
  return record.status === "FAILED";
}

function isToday(value: string) {
  const date = new Date(value);
  const today = new Date();
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

function formatInboxListDate(value: string) {
  return isToday(value)
    ? listTimeFormatter.format(new Date(value))
    : recordDateFormatter.format(new Date(value));
}

function CaptureIcon({ type }: { type: CaptureType }) {
  const Icon =
    type === "QUICK_NOTE"
      ? PencilLine
      : type === "PASTE"
        ? ClipboardPaste
        : type === "RECORDING"
          ? Mic2
          : type === "AUDIO_IMPORT"
            ? AudioLines
            : type === "DOCUMENT_IMPORT"
              ? FileText
              : Layers3;
  return <Icon aria-hidden="true" className="size-4" />;
}

type InboxPageProps = {
  search: InboxSearch;
  onSearchChange: (search: InboxSearch) => void;
};

export function InboxPage({ search, onSearchChange }: InboxPageProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewOpen, setPreviewOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [bulkAction, setBulkAction] = useState<
    "classify" | "upgrade" | "delete" | null
  >(null);
  const [bulkCourseId, setBulkCourseId] = useState<string | null>(null);
  const [bulkPending, setBulkPending] = useState(false);
  const records = useQuery({
    queryKey: recordKeys.inbox(),
    queryFn: () => recordApi.listInbox(),
    refetchInterval: (query) =>
      query.state.data?.some((record) => record.status === "CONTENT_PROCESSING")
        ? 2_000
        : false,
  });

  const allRecords = records.data ?? [];
  const typeFilter = search.type ?? "all";
  const statusFilter = search.status ?? "unfiled";
  const normalizedQuery = search.q?.trim().toLocaleLowerCase() ?? "";
  const filteredRecords = allRecords.filter((record) => {
    if (
      !matchesType(record, typeFilter) ||
      !matchesStatus(record, statusFilter)
    )
      return false;
    if (!normalizedQuery) return true;
    return [
      record.title,
      t(captureTypeLabelKeys[record.capture_type]),
      t(statusLabelKeys[record.status]),
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedQuery);
  });
  const pageCount = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
  const page = Math.min(search.page ?? 1, pageCount);
  const pageRecords = filteredRecords.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );
  const selectedRecord = search.record
    ? (allRecords.find((record) => record.id === search.record) ?? null)
    : null;
  const selectedOnPage = pageRecords.filter((record) =>
    selectedIds.has(record.id),
  );
  const selectedRecords = allRecords.filter((record) =>
    selectedIds.has(record.id),
  );
  const allPageSelected =
    pageRecords.length > 0 && selectedOnPage.length === pageRecords.length;
  const allSelectedOrganizable =
    selectedRecords.length > 0 &&
    selectedRecords.every((record) => ORGANIZABLE_STATUSES.has(record.status));
  const stats = {
    today: allRecords.filter((record) => isToday(record.created_at)).length,
    unfiled: allRecords.length,
    upgradable: allRecords.filter((record) =>
      ORGANIZABLE_STATUSES.has(record.status),
    ).length,
  };

  function updateSearch(next: Partial<InboxSearch>) {
    onSearchChange({ ...search, ...next });
  }

  function changeFilter(next: Partial<InboxSearch>) {
    setSelectedIds(new Set());
    updateSearch({ ...next, page: undefined, record: undefined });
  }

  function toggleRecord(recordId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(recordId);
      else next.delete(recordId);
      return next;
    });
  }

  function openPreview(recordId: string) {
    updateSearch({ record: recordId });
    if (window.innerWidth < 1280) setPreviewOpen(true);
  }

  function closeBulkDialog() {
    if (bulkPending) return;
    setBulkAction(null);
    setBulkCourseId(null);
  }

  async function executeBulkAction() {
    if (!bulkAction || !selectedRecords.length) return;
    if (bulkAction !== "delete" && !bulkCourseId) return;
    setBulkPending(true);
    const courseId = bulkCourseId;
    const results = await Promise.allSettled(
      selectedRecords.map((record) => {
        if (bulkAction === "delete") return recordApi.delete(record.id);
        if (bulkAction === "classify")
          return recordApi.classify(record.id, courseId ?? "");
        return recordApi.upgrade(record.id, courseId ?? "");
      }),
    );
    const failedIds = new Set(
      results.flatMap((result, index) =>
        result.status === "rejected" ? [selectedRecords[index].id] : [],
      ),
    );
    const succeeded = selectedRecords.filter(
      (record) => !failedIds.has(record.id),
    );

    for (const record of succeeded) {
      if (bulkAction === "delete") {
        queryClient.removeQueries({
          queryKey: recordKeys.detail(record.id),
          exact: true,
        });
        queryClient.removeQueries({
          queryKey: recordKeys.transcript(record.id),
          exact: true,
        });
      } else if (bulkAction === "upgrade") {
        void queryClient.invalidateQueries({
          queryKey: recordKeys.detail(record.id),
        });
        void queryClient.invalidateQueries({
          queryKey: recordKeys.summary(record.id),
        });
      }
    }
    if (courseId) {
      await queryClient.invalidateQueries({
        queryKey: recordKeys.courseList(courseId),
      });
    }
    await queryClient.invalidateQueries({ queryKey: recordKeys.inbox() });
    setSelectedIds(failedIds);
    setFeedback(
      t("inbox.bulk.result", {
        success: succeeded.length,
        failed: failedIds.size,
      }),
    );
    setBulkPending(false);
    setBulkAction(null);
    setBulkCourseId(null);
  }

  if (records.isPending) {
    return <InboxLoading title={t("inbox.title")} label={t("inbox.loading")} />;
  }

  if (records.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("inbox.title")}
        </h1>
        <h2 className="text-section font-section text-ink mt-6">
          {t("inbox.errorTitle")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {records.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void records.refetch()}
        >
          {t("inbox.retry")}
        </Button>
      </section>
    );
  }

  if (records.data.length === 0) {
    return (
      <section className="work-surface-enter max-w-workbench px-content mx-auto min-h-full py-8">
        <InboxHeader stats={stats} />
        {feedback ? (
          <p role="status" className="text-body text-muted-foreground mt-4">
            {feedback}
          </p>
        ) : null}
        <Empty className="border-border mt-8 items-start rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-start">
          <EmptyHeader className="items-start text-start">
            <EmptyMedia className="text-muted-foreground">
              <Inbox aria-hidden="true" className="size-5" />
            </EmptyMedia>
            <h2 className="text-section font-section text-ink">
              {t("inbox.emptyTitle")}
            </h2>
            <EmptyDescription className="max-w-reading text-body text-start">
              {t("inbox.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-h-full min-w-0 py-8">
      <InboxHeader stats={stats} />
      {feedback ? (
        <p role="status" className="text-body text-muted-foreground mt-4">
          {feedback}
        </p>
      ) : null}

      <div className="mt-5 grid min-h-0 gap-3 xl:grid-cols-[minmax(0,1fr)_clamp(22.5rem,30vw,31rem)]">
        <div className="min-w-0">
          <div className="border-border bg-background rounded-xl border p-3 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
            <div className="flex flex-wrap items-center gap-2">
              <Tabs
                value={typeFilter}
                onValueChange={(value) =>
                  changeFilter({
                    type:
                      isInboxTypeFilter(value) && value !== "all"
                        ? value
                        : undefined,
                  })
                }
              >
                <TabsList
                  aria-label={t("inbox.filters.typeLabel")}
                  className="border-border bg-background h-9 rounded-lg border p-1 shadow-none"
                >
                  {typeFilters.map((value) => (
                    <TabsTrigger
                      key={value}
                      value={value}
                      className="data-active:bg-filter-active-background data-active:text-filter-active-foreground h-7 rounded-md px-2.5 text-[13px] data-active:border-transparent data-active:shadow-sm"
                    >
                      {t(`inbox.filters.type.${value}`)}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <div
                className="border-border bg-background flex h-9 items-center gap-0.5 rounded-lg border p-1"
                aria-label={t("inbox.filters.statusLabel")}
              >
                {statusFilters.map((value) => (
                  <Button
                    key={value}
                    type="button"
                    variant="ghost"
                    size="sm"
                    className={`h-7 rounded-md px-2.5 text-[13px] ${statusFilter === value ? "bg-muted text-foreground shadow-sm" : "text-muted-foreground"}`}
                    onClick={() =>
                      changeFilter({
                        status: value === "unfiled" ? undefined : value,
                      })
                    }
                  >
                    {t(`inbox.filters.status.${value}`)}
                  </Button>
                ))}
              </div>
              <div className="relative ml-auto min-w-52 flex-1 lg:max-w-64">
                <Search
                  aria-hidden="true"
                  className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
                />
                <Input
                  type="search"
                  value={search.q ?? ""}
                  onChange={(event) =>
                    changeFilter({ q: event.target.value || undefined })
                  }
                  maxLength={100}
                  className="bg-background h-9 rounded-lg pl-8"
                  aria-label={t("inbox.filters.searchLabel")}
                  placeholder={t("inbox.filters.searchPlaceholder")}
                />
              </div>
              <Button
                variant="outline"
                size="icon"
                className="size-9 rounded-lg"
                aria-label={t("inbox.filters.more")}
              >
                <SlidersHorizontal aria-hidden="true" />
              </Button>
            </div>
          </div>

          <div className="border-border bg-background mt-3 flex min-h-12 items-center gap-3 rounded-xl border px-4 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
            <Checkbox
              checked={allPageSelected}
              onCheckedChange={(checked) => {
                const next = new Set(selectedIds);
                pageRecords.forEach((record) => {
                  if (checked) next.add(record.id);
                  else next.delete(record.id);
                });
                setSelectedIds(next);
              }}
              aria-label={t("inbox.selection.page")}
            />
            {selectedIds.size ? (
              <>
                <span className="text-label text-muted-foreground">
                  {t("inbox.selection.count", { count: selectedIds.size })}
                </span>
                <Button
                  variant="ghost"
                  size="xs"
                  className="bg-blue-50 text-blue-600 hover:bg-blue-100 hover:text-blue-700 dark:bg-blue-950/50 dark:text-blue-300"
                  onClick={() => setSelectedIds(new Set())}
                >
                  {t("inbox.selection.clear")}
                </Button>
                <div className="ml-auto flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!allSelectedOrganizable}
                    onClick={() => setBulkAction("classify")}
                  >
                    <FolderOpen aria-hidden="true" />
                    {t("inbox.bulk.classify")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!allSelectedOrganizable}
                    onClick={() => setBulkAction("upgrade")}
                  >
                    <Rocket aria-hidden="true" />
                    {t("inbox.bulk.upgrade")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => setBulkAction("delete")}
                  >
                    <Trash2 aria-hidden="true" />
                    {t("inbox.bulk.delete")}
                  </Button>
                </div>{" "}
              </>
            ) : (
              <span className="text-label text-muted-foreground">
                {t("inbox.listCount", { count: filteredRecords.length })}
              </span>
            )}
          </div>

          <div className="text-muted-foreground grid grid-cols-[1rem_minmax(0,1fr)_5.5rem_7rem] items-center gap-3 px-4 py-3 text-xs 2xl:grid-cols-[1rem_minmax(0,1fr)_5.5rem_7rem_7rem_6rem]">
            <span />
            <span>{t("inbox.columns.content")}</span>
            <span>{t("inbox.columns.source")}</span>
            <span>{t("inbox.columns.status")}</span>
            <span className="hidden 2xl:block">
              {t("inbox.columns.course")}
            </span>
            <span className="hidden text-right 2xl:block">
              {t("inbox.columns.createdAt")}
            </span>
          </div>

          {pageRecords.length ? (
            <ul aria-label={t("inbox.listLabel")} className="min-w-0 space-y-2">
              {pageRecords.map((record) => (
                <InboxRow
                  key={record.id}
                  record={record}
                  selected={record.id === selectedRecord?.id}
                  checked={selectedIds.has(record.id)}
                  onCheckedChange={(checked) =>
                    toggleRecord(record.id, checked)
                  }
                  onPreview={() => openPreview(record.id)}
                  onClassified={(courseName) =>
                    setFeedback(
                      t("inbox.classifiedFeedback", { course: courseName }),
                    )
                  }
                />
              ))}
            </ul>
          ) : (
            <Empty className="items-start rounded-none px-2 py-10 text-start">
              <EmptyHeader className="items-start text-start">
                <h2 className="text-section font-section text-ink">
                  {t("inbox.noResultsTitle")}
                </h2>
                <EmptyDescription>
                  {t("inbox.noResultsDescription")}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent className="items-start">
                <Button
                  variant="outline"
                  onClick={() =>
                    changeFilter({
                      q: undefined,
                      type: undefined,
                      status: undefined,
                    })
                  }
                >
                  {t("inbox.filters.clear")}
                </Button>
              </EmptyContent>
            </Empty>
          )}

          {filteredRecords.length > PAGE_SIZE ? (
            <nav
              className="mt-5 flex items-center justify-end gap-2"
              aria-label={t("inbox.pagination.label")}
            >
              <span className="text-label text-muted-foreground mr-2 tabular-nums">
                {t("inbox.pagination.page", { page, count: pageCount })}
              </span>
              <Button
                variant="outline"
                size="icon"
                disabled={page <= 1}
                aria-label={t("inbox.pagination.previous")}
                onClick={() =>
                  updateSearch({
                    page: page - 1 || undefined,
                    record: undefined,
                  })
                }
              >
                <ArrowLeft aria-hidden="true" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                disabled={page >= pageCount}
                aria-label={t("inbox.pagination.next")}
                onClick={() =>
                  updateSearch({ page: page + 1, record: undefined })
                }
              >
                <ArrowRight aria-hidden="true" />
              </Button>
            </nav>
          ) : null}
        </div>

        <aside className="border-border bg-background sticky top-4 hidden max-h-[calc(100vh-var(--spacing-titlebar)-7rem)] min-h-[calc(100vh-var(--spacing-titlebar)-9.5rem)] min-w-0 self-start overflow-y-auto rounded-xl border shadow-[0_4px_16px_rgb(15_23_42/0.045)] xl:block">
          <InboxPreview
            record={selectedRecord}
            onClose={() => updateSearch({ record: undefined })}
            onClassified={(courseName) =>
              setFeedback(t("inbox.classifiedFeedback", { course: courseName }))
            }
          />
        </aside>
      </div>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl xl:hidden">
          <DialogHeader className="sr-only">
            <DialogTitle>{t("inbox.preview.title")}</DialogTitle>
            <DialogDescription>
              {t("inbox.preview.description")}
            </DialogDescription>
          </DialogHeader>
          <InboxPreview
            record={selectedRecord}
            onClassified={(courseName) =>
              setFeedback(t("inbox.classifiedFeedback", { course: courseName }))
            }
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={bulkAction !== null}
        onOpenChange={(open) => {
          if (!open) closeBulkDialog();
        }}
      >
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {bulkAction
                ? t(`inbox.bulk.dialog.${bulkAction}.title`, {
                    count: selectedRecords.length,
                  })
                : ""}
            </DialogTitle>
            <DialogDescription>
              {bulkAction
                ? t(`inbox.bulk.dialog.${bulkAction}.description`, {
                    count: selectedRecords.length,
                  })
                : ""}
            </DialogDescription>
          </DialogHeader>
          {bulkAction === "classify" || bulkAction === "upgrade" ? (
            <ActiveCourseSelect
              id="inbox-bulk-course"
              value={bulkCourseId}
              onValueChange={setBulkCourseId}
              disabled={bulkPending}
            />
          ) : null}
          <DialogFooter>
            <DialogClose
              render={<Button variant="outline" disabled={bulkPending} />}
            >
              {t("inbox.bulk.cancel")}
            </DialogClose>
            <Button
              variant={bulkAction === "delete" ? "destructive" : "default"}
              disabled={
                bulkPending || (bulkAction !== "delete" && !bulkCourseId)
              }
              onClick={() => void executeBulkAction()}
            >
              {bulkPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("inbox.bulk.submitting")}
                />
              ) : null}
              {bulkAction ? t(`inbox.bulk.dialog.${bulkAction}.confirm`) : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function InboxHeader({
  stats,
}: {
  stats: { today: number; unfiled: number; upgradable: number };
}) {
  const { t } = useTranslation();
  const items = [
    {
      key: "today",
      value: stats.today,
      icon: FilePlus2,
      iconClass:
        "bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-300",
    },
    {
      key: "unfiled",
      value: stats.unfiled,
      icon: ListTodo,
      iconClass:
        "bg-orange-50 text-orange-600 dark:bg-orange-950/50 dark:text-orange-300",
    },
    {
      key: "upgradable",
      value: stats.upgradable,
      icon: Rocket,
      iconClass:
        "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300",
    },
  ] as const;
  return (
    <header className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <h1 className="text-headline font-headline text-ink-strong">
          {t("inbox.title")}
        </h1>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {t("inbox.description")}
        </p>
      </div>
      <dl className="border-border bg-background grid min-w-[30rem] grid-cols-3 rounded-xl border px-2 py-3 shadow-[0_4px_14px_rgb(15_23_42/0.05)]">
        {items.map(({ key, value, icon: Icon, iconClass }, index) => (
          <div
            key={key}
            className={`flex items-center gap-3 px-4 ${index ? "border-border border-l" : ""}`}
          >
            <span
              className={`${iconClass} flex size-9 shrink-0 items-center justify-center rounded-full`}
            >
              <Icon aria-hidden="true" className="size-[18px]" />
            </span>
            <div>
              <dt className="text-foreground text-[13px] font-semibold">
                {t(`inbox.stats.${key}`)}
              </dt>
              <dd className="text-foreground mt-0.5 flex items-baseline gap-1.5 text-2xl font-semibold tabular-nums">
                {value}
                <span className="text-muted-foreground text-xs font-normal">
                  {t("inbox.stats.unit")}
                </span>
              </dd>
            </div>
          </div>
        ))}
      </dl>
    </header>
  );
}

function InboxLoading({ title, label }: { title: string; label: string }) {
  return (
    <section className="max-w-workbench px-content mx-auto py-8">
      <h1 className="text-headline font-headline text-ink-strong">{title}</h1>
      <p
        role="status"
        className="text-body text-muted-foreground mt-6 flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {label}
      </p>
    </section>
  );
}

function InboxRow({
  record,
  selected,
  checked,
  onCheckedChange,
  onPreview,
  onClassified,
}: {
  record: InboxRecordOut;
  selected: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onPreview: () => void;
  onClassified: (courseName: string) => void;
}) {
  const { t } = useTranslation();
  const title = record.title.trim() || t("spaces.records.untitled");
  const meta = inboxMetaText(record, t);
  return (
    <li
      className={`group border-border bg-background relative grid min-h-[72px] min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-xl border px-4 shadow-[0_1px_2px_rgb(15_23_42/0.035)] transition-[border-color,background-color,box-shadow] ${selected ? "border-foreground/25 bg-surface-subtle shadow-[0_3px_10px_rgb(15_23_42/0.06)]" : "hover:border-foreground/20 hover:shadow-[0_3px_10px_rgb(15_23_42/0.05)]"}`}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={t("inbox.selection.record", { title })}
      />
      <button
        type="button"
        onClick={onPreview}
        className="focus-visible:ring-ring/40 grid min-w-0 grid-cols-[minmax(0,1fr)_5.5rem_7rem] items-center gap-3 py-3 text-left focus-visible:rounded-lg focus-visible:ring-3 focus-visible:outline-hidden 2xl:grid-cols-[minmax(0,1fr)_5.5rem_7rem_7rem_6rem]"
        aria-label={t("inbox.preview.action", { title })}
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="border-border bg-surface-subtle text-foreground flex size-10 shrink-0 items-center justify-center rounded-lg border">
            <CaptureIcon type={record.capture_type} />
          </span>
          <span className="min-w-0">
            <span
              className="text-body text-foreground block truncate font-semibold"
              title={title}
            >
              {title}
            </span>
            <span className="text-label text-muted-foreground mt-0.5 block truncate">
              {meta || t("inbox.row.unfiled")}
            </span>
          </span>
        </span>
        <span className="text-label text-muted-foreground truncate">
          {t(captureTypeLabelKeys[record.capture_type])}
        </span>
        <span
          className={`${inboxStatusClassNames[record.status]} text-label font-label justify-self-start rounded-md px-2 py-1 whitespace-nowrap`}
        >
          {t(statusLabelKeys[record.status])}
        </span>
        <span className="text-label text-muted-foreground hidden truncate 2xl:block">
          {t("inbox.row.unfiledShort")}
        </span>
        <time
          className="text-label text-muted-foreground hidden text-right tabular-nums 2xl:block"
          dateTime={record.created_at}
        >
          {formatInboxListDate(record.created_at)}
        </time>
      </button>
      <div className="bg-background/95 absolute right-3 flex items-center gap-1 rounded-lg pl-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
        <div>
          <InboxRowActions
            record={record}
            onClassified={onClassified}
            compact
          />
        </div>
        <Link
          to="/records/$recordId"
          params={{ recordId: record.id }}
          search={{ tab: "transcript" }}
          className="hover:bg-surface-subtle focus-visible:ring-ring/40 text-muted-foreground flex size-8 items-center justify-center rounded-sm focus-visible:ring-3"
          aria-label={t("inbox.openRecord", { title })}
        >
          <FolderOpen aria-hidden="true" className="size-4" />
        </Link>
      </div>
    </li>
  );
}

function InboxPreview({
  record,
  onClose,
  onClassified,
}: {
  record: InboxRecordOut | null;
  onClose?: () => void;
  onClassified: (courseName: string) => void;
}) {
  const { t } = useTranslation();
  const transcript = useQuery({
    queryKey: recordKeys.transcript(record?.id ?? "none"),
    queryFn: () => recordApi.getTranscript(record?.id ?? ""),
    enabled: Boolean(record),
  });

  if (!record) {
    return (
      <Empty className="h-full min-h-72 rounded-none border-0 px-5 text-start">
        <EmptyHeader className="items-start text-start">
          <h2 className="text-section font-section text-ink">
            {t("inbox.preview.emptyTitle")}
          </h2>
          <EmptyDescription>
            {t("inbox.preview.emptyDescription")}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const title = record.title.trim() || t("spaces.records.untitled");
  const content = transcript.data?.transcript?.content;
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-start justify-between gap-3 px-5 pt-5">
        <div>
          <p className="text-label text-muted-foreground">
            {t("inbox.preview.title")}
          </p>
          <span className="mt-2 inline-flex rounded-md bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-950/45 dark:text-blue-300">
            {t(captureTypeLabelKeys[record.capture_type])}
          </span>
        </div>
        {onClose ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("inbox.preview.close")}
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <h2 className="text-foreground mt-5 px-5 text-base leading-6 font-semibold break-words">
        {title}
      </h2>
      <time
        className="text-label text-muted-foreground mt-2 px-5 tabular-nums"
        dateTime={record.created_at}
      >
        {recordDateFormatter.format(new Date(record.created_at))}
      </time>
      <div className="border-border mx-5 mt-5 border-b pb-5">
        {transcript.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("inbox.preview.loading")}
          </p>
        ) : transcript.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{t("inbox.preview.error")}</AlertDescription>
          </Alert>
        ) : content ? (
          <p className="text-body text-ink max-h-48 overflow-y-auto whitespace-pre-wrap">
            {content}
          </p>
        ) : (
          <p className="text-body text-muted-foreground">
            {t(`inbox.preview.availability.${record.status}`)}
          </p>
        )}
      </div>
      <div className="border-border mt-0 border-b px-5 py-5">
        <h3 className="text-foreground text-sm font-semibold">
          {t("inbox.preview.metadata")}
        </h3>
        <dl className="mt-4 grid grid-cols-[6rem_1fr] gap-x-3 gap-y-3 text-sm">
          <dt className="text-muted-foreground">{t("inbox.preview.source")}</dt>
          <dd className="text-ink">
            {t(captureTypeLabelKeys[record.capture_type])}
          </dd>
          <dt className="text-muted-foreground">{t("inbox.preview.status")}</dt>
          <dd>
            <span
              className={`${inboxStatusClassNames[record.status]} text-label rounded-md px-2 py-1`}
            >
              {t(statusLabelKeys[record.status])}
            </span>
          </dd>
          <dt className="text-muted-foreground">
            {t("inbox.preview.createdAt")}
          </dt>
          <dd className="text-ink tabular-nums">
            {recordDateFormatter.format(new Date(record.created_at))}
          </dd>
          <dt className="text-muted-foreground">
            {t("inbox.preview.characters")}
          </dt>
          <dd className="text-ink tabular-nums">{record.content_chars ?? 0}</dd>
          <dt className="text-muted-foreground">{t("inbox.preview.course")}</dt>
          <dd className="text-ink">{t("inbox.row.unfiledShort")}</dd>
        </dl>
      </div>
      <div className="bg-background sticky bottom-0 mt-auto flex flex-wrap items-center gap-2 p-4">
        <InboxRowActions record={record} onClassified={onClassified} />
        <Button
          nativeButton={false}
          variant="outline"
          size="sm"
          render={
            <Link
              to="/records/$recordId"
              params={{ recordId: record.id }}
              search={{ tab: "transcript" }}
            />
          }
        >
          {t("inbox.openRecordShort")}
        </Button>
      </div>
    </div>
  );
}
