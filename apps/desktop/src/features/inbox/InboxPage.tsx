import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  ClipboardPaste,
  FileText,
  FolderOpen,
  Inbox,
  Layers3,
  Mic2,
  PencilLine,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { CaptureType, RecordOut } from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";

const PAGE_SIZE = 20;
const ORGANIZABLE_STATUSES = new Set(["NOTE", "SUMMARY_PENDING"]);
const PROCESSING_STATUSES = new Set([
  "DRAFT",
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

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

const demoContent: Record<string, string> = {
  "demo-note":
    "向量空间是线性代数的核心概念。它由向量集合以及加法、数乘两种运算构成，并满足封闭性与相应公理。理解基、维数和线性无关，是继续学习线性映射的基础。",
  "demo-paste":
    "函数极限描述自变量趋近某个值时函数值的变化趋势。判断极限时需要先确认定义域，再选择代数化简、夹逼或等价无穷小等方法。",
  "demo-audio":
    "课堂录音正在转写。完成后会在此显示可检索的正文，并保留原始时间轴供后续回看。",
  "demo-document":
    "本章介绍定积分的定义、几何意义与基本性质，并通过面积和累积量说明微积分基本定理的联系。",
  "demo-recording":
    "微分方程方法总结：先识别方程类型，再决定分离变量、常数变易或特征根方法。",
  "demo-clip":
    "复数可以写作 a + bi，在复平面中对应点 (a, b)。模长与辐角为乘除和幂运算提供了更直观的表示。",
};

function createDemoRecords(): RecordOut[] {
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const at = (date: Date, hour: number, minute: number) => {
    const value = new Date(date);
    value.setHours(hour, minute, 0, 0);
    return value.toISOString();
  };
  const record = (
    id: string,
    capture_type: CaptureType,
    title: string,
    status: RecordOut["status"],
    created_at: string,
    duration_ms = 0,
  ): RecordOut => ({
    id,
    course_id: null,
    capture_type,
    title,
    status,
    duration_ms,
    summary_confirmed_at: null,
    created_at,
    updated_at: created_at,
  });

  return [
    record(
      "demo-note",
      "QUICK_NOTE",
      "线性代数 · 向量空间的定义与性质",
      "NOTE",
      at(now, 10, 32),
    ),
    record(
      "demo-paste",
      "PASTE",
      "从《高等数学（上）》第 12 讲复制的文本",
      "SUMMARY_PENDING",
      at(now, 9, 58),
    ),
    record(
      "demo-audio",
      "AUDIO_IMPORT",
      "线代第 3 章 线性相关性 课堂录音",
      "CONTENT_PROCESSING",
      at(yesterday, 16, 30),
      2_061_000,
    ),
    record(
      "demo-document",
      "DOCUMENT_IMPORT",
      "高数上 第四章 定积分的应用 讲义.pdf",
      "SUMMARY_PENDING",
      at(yesterday, 14, 2),
    ),
    record(
      "demo-recording",
      "RECORDING",
      "微分方程方法总结（个人复盘）",
      "CONTENT_PROCESSING",
      at(yesterday, 10, 11),
      1_687_000,
    ),
    record(
      "demo-clip",
      "CLIP",
      "复数的几何表示与运算",
      "NOTE",
      at(yesterday, 8, 46),
    ),
  ];
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
  const [demoRequested, setDemoRequested] = useState(false);
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

  const demoRecords = useMemo(() => createDemoRecords(), []);
  const demoMode = demoRequested && records.data?.length === 0;
  const allRecords = demoMode ? demoRecords : (records.data ?? []);
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

  if (records.data.length === 0 && !demoMode) {
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
          <EmptyContent className="items-start">
            <Button variant="outline" onClick={() => setDemoRequested(true)}>
              {t("inbox.demo.open")}
            </Button>
          </EmptyContent>
        </Empty>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-h-full min-w-0 py-8">
      <InboxHeader stats={stats} />
      {demoMode ? (
        <Alert className="border-border bg-surface-subtle mt-5 pr-24">
          <Sparkles aria-hidden="true" />
          <AlertDescription>{t("inbox.demo.description")}</AlertDescription>
          <Button
            variant="ghost"
            size="sm"
            className="absolute top-1.5 right-2"
            onClick={() => {
              setDemoRequested(false);
              setSelectedIds(new Set());
              onSearchChange({});
            }}
          >
            {t("inbox.demo.close")}
          </Button>
        </Alert>
      ) : null}
      {feedback ? (
        <p role="status" className="text-body text-muted-foreground mt-4">
          {feedback}
        </p>
      ) : null}

      <div className="border-border mt-5 border-y py-3">
        <div className="flex flex-wrap items-center gap-3">
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
            <TabsList aria-label={t("inbox.filters.typeLabel")}>
              {typeFilters.map((value) => (
                <TabsTrigger key={value} value={value}>
                  {t(`inbox.filters.type.${value}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div
            className="bg-border hidden h-5 w-px lg:block"
            aria-hidden="true"
          />
          <div
            className="flex items-center gap-1"
            aria-label={t("inbox.filters.statusLabel")}
          >
            {statusFilters.map((value) => (
              <Button
                key={value}
                type="button"
                variant={statusFilter === value ? "secondary" : "ghost"}
                size="sm"
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
              className="pl-8"
              aria-label={t("inbox.filters.searchLabel")}
              placeholder={t("inbox.filters.searchPlaceholder")}
            />
          </div>
        </div>
      </div>

      <div className="mt-4 grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_22.5rem]">
        <div className="min-w-0">
          <div className="border-border flex min-h-11 items-center gap-3 border-b px-2">
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
                  onClick={() => setSelectedIds(new Set())}
                >
                  {t("inbox.selection.clear")}
                </Button>
                {demoMode ? (
                  <div className="ml-auto flex items-center gap-1">
                    <span className="text-label text-muted-foreground mr-1 hidden 2xl:inline">
                      {t("inbox.demo.readOnly")}
                    </span>
                    <Button variant="ghost" size="sm" disabled>
                      {t("inbox.bulk.classify")}
                    </Button>
                    <Button variant="ghost" size="sm" disabled>
                      {t("inbox.bulk.upgrade")}
                    </Button>
                    <Button variant="ghost" size="sm" disabled>
                      {t("inbox.bulk.delete")}
                    </Button>
                  </div>
                ) : (
                  <div className="ml-auto flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!allSelectedOrganizable}
                      onClick={() => setBulkAction("classify")}
                    >
                      {t("inbox.bulk.classify")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!allSelectedOrganizable}
                      onClick={() => setBulkAction("upgrade")}
                    >
                      {t("inbox.bulk.upgrade")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setBulkAction("delete")}
                    >
                      {t("inbox.bulk.delete")}
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <span className="text-label text-muted-foreground">
                {t("inbox.listCount", { count: filteredRecords.length })}
              </span>
            )}
          </div>

          {pageRecords.length ? (
            <ul aria-label={t("inbox.listLabel")} className="min-w-0">
              {pageRecords.map((record) => (
                <InboxRow
                  key={record.id}
                  record={record}
                  selected={record.id === selectedRecord?.id}
                  checked={selectedIds.has(record.id)}
                  demo={demoMode}
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

        <aside className="border-border sticky top-4 hidden max-h-[calc(100vh-7rem)] min-w-0 self-start overflow-y-auto border-l pl-4 xl:block">
          <InboxPreview
            record={selectedRecord}
            demo={demoMode}
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
            demo={demoMode}
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
      <dl className="border-border bg-surface-raised grid min-w-80 grid-cols-3 rounded-md border">
        {(
          [
            ["today", stats.today],
            ["unfiled", stats.unfiled],
            ["upgradable", stats.upgradable],
          ] as const
        ).map(([key, value], index) => (
          <div
            key={key}
            className={`px-4 py-3 ${index ? "border-border border-l" : ""}`}
          >
            <dt className="text-label text-muted-foreground">
              {t(`inbox.stats.${key}`)}
            </dt>
            <dd className="text-ink-strong mt-0.5 text-xl font-semibold tabular-nums">
              {value}
            </dd>
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
  demo,
  onCheckedChange,
  onPreview,
  onClassified,
}: {
  record: RecordOut;
  selected: boolean;
  checked: boolean;
  demo: boolean;
  onCheckedChange: (checked: boolean) => void;
  onPreview: () => void;
  onClassified: (courseName: string) => void;
}) {
  const { t } = useTranslation();
  const title = record.title.trim() || t("spaces.records.untitled");
  return (
    <li
      className={`group border-border grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border-b px-2 transition-colors ${selected ? "bg-surface-strong" : "hover:bg-surface-subtle"}`}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={t("inbox.selection.record", { title })}
      />
      <button
        type="button"
        onClick={onPreview}
        className="focus-visible:ring-ring/40 grid min-w-0 grid-cols-[minmax(0,1fr)_5.5rem_7rem] items-center gap-3 py-3 text-left focus-visible:ring-3 focus-visible:outline-hidden"
        aria-label={t("inbox.preview.action", { title })}
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="border-border text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-sm border">
            <CaptureIcon type={record.capture_type} />
          </span>
          <span className="min-w-0">
            <span
              className="text-body font-section text-ink block truncate"
              title={title}
            >
              {title}
            </span>
            <span className="text-label text-muted-foreground mt-0.5 block truncate">
              {demoContent[record.id] ?? t("inbox.row.unfiled")}
            </span>
          </span>
        </span>
        <span className="text-label text-muted-foreground truncate">
          {t(captureTypeLabelKeys[record.capture_type])}
        </span>
        <span
          className={`${statusClassNames[record.status]} text-label font-label justify-self-start rounded-xs px-2 py-1 whitespace-nowrap`}
        >
          {t(statusLabelKeys[record.status])}
        </span>
      </button>
      <div className="flex items-center gap-1">
        <time
          className="text-label text-muted-foreground hidden w-24 text-right tabular-nums 2xl:block"
          dateTime={record.created_at}
        >
          {recordDateFormatter.format(new Date(record.created_at))}
        </time>
        <div className="opacity-70 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
          <InboxRowActions
            record={record}
            onClassified={onClassified}
            compact
            disabled={demo}
          />
        </div>
        {!demo ? (
          <Link
            to="/records/$recordId"
            params={{ recordId: record.id }}
            search={{ tab: "transcript" }}
            className="hover:bg-surface-subtle focus-visible:ring-ring/40 text-muted-foreground flex size-8 items-center justify-center rounded-sm focus-visible:ring-3"
            aria-label={t("inbox.openRecord", { title })}
          >
            <FolderOpen aria-hidden="true" className="size-4" />
          </Link>
        ) : null}
      </div>
    </li>
  );
}

function InboxPreview({
  record,
  demo,
  onClose,
  onClassified,
}: {
  record: RecordOut | null;
  demo: boolean;
  onClose?: () => void;
  onClassified: (courseName: string) => void;
}) {
  const { t } = useTranslation();
  const transcript = useQuery({
    queryKey: recordKeys.transcript(record?.id ?? "none"),
    queryFn: () => recordApi.getTranscript(record?.id ?? ""),
    enabled: Boolean(record && !demo),
  });

  if (!record) {
    return (
      <Empty className="h-full min-h-72 rounded-none border-0 px-4 text-start">
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
  const content = demo
    ? demoContent[record.id]
    : transcript.data?.transcript?.content;
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-label text-muted-foreground">
            {t("inbox.preview.title")}
          </p>
          <span className="text-label bg-surface-subtle text-muted-foreground mt-2 inline-flex rounded-xs px-2 py-1">
            {demo
              ? t("inbox.demo.badge")
              : t(captureTypeLabelKeys[record.capture_type])}
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
      <h2 className="text-section font-section text-ink-strong mt-5 break-words">
        {title}
      </h2>
      <time
        className="text-label text-muted-foreground mt-2 tabular-nums"
        dateTime={record.created_at}
      >
        {recordDateFormatter.format(new Date(record.created_at))}
      </time>
      <div className="border-border mt-5 border-b pb-5">
        {transcript.isPending && !demo ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("inbox.preview.loading")}
          </p>
        ) : transcript.isError && !demo ? (
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
      <dl className="border-border grid grid-cols-[6rem_1fr] gap-x-3 gap-y-3 border-b py-5 text-sm">
        <dt className="text-muted-foreground">{t("inbox.preview.source")}</dt>
        <dd className="text-ink">
          {t(captureTypeLabelKeys[record.capture_type])}
        </dd>
        <dt className="text-muted-foreground">{t("inbox.preview.status")}</dt>
        <dd>
          <span
            className={`${statusClassNames[record.status]} text-label rounded-xs px-2 py-1`}
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
        <dd className="text-ink tabular-nums">{content?.length ?? 0}</dd>
        <dt className="text-muted-foreground">{t("inbox.preview.course")}</dt>
        <dd className="text-ink">{t("inbox.row.unfiled")}</dd>
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {demo ? (
          <>
            <InboxRowActions
              record={record}
              onClassified={onClassified}
              disabled
            />
            <p className="text-label text-muted-foreground basis-full">
              {t("inbox.demo.readOnly")}
            </p>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}
