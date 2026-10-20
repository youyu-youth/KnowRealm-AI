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
  Rocket,
  Trash2,
  X,
} from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
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
import { Spinner } from "@/components/ui/spinner";
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import { InboxCard } from "@/features/inbox/InboxCard";
import { InboxCourseTray } from "@/features/inbox/InboxCourseTray";
import { InboxToolbar } from "@/features/inbox/InboxToolbar";
import { InboxRowActions } from "@/features/inbox/InboxRowActions";
import {
  type InboxSearch,
  type InboxStatusFilter,
  type InboxTypeFilter,
} from "@/features/inbox/inboxSearch";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type {
  CaptureType,
  InboxRecordOut,
  RecordOut,
} from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  recordDateFormatter,
  statusLabelKeys,
} from "@/features/records/recordPresentation";

import {
  ORGANIZABLE_STATUSES,
  PROCESSING_STATUSES,
  inboxStatusClassNames,
  inboxMetaText,
  formatInboxListDate,
} from "@/features/inbox/inboxPresentation";

const PAGE_SIZE = 20;
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
  const [previewOpen, setPreviewOpen] = useState(
    Boolean(search.record) &&
      (search.view !== "list" || window.innerWidth < 1280),
  );
  const [draggedIds, setDraggedIds] = useState<string[]>([]);
  const bulkPendingRef = useRef(false);
  const view = search.view ?? "desk";
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
  filteredRecords.sort((a, b) => {
    if (search.sort === "title") return a.title.localeCompare(b.title);
    const order =
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime() ||
      b.id.localeCompare(a.id);
    return search.sort === "oldest" ? -order : order;
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
    if (view === "desk" || window.innerWidth < 1280) setPreviewOpen(true);
  }

  function closeBulkDialog() {
    if (bulkPending) return;
    setBulkAction(null);
    setBulkCourseId(null);
  }

  async function executeBulkAction() {
    if (bulkPendingRef.current) return;
    if (!bulkAction || !selectedRecords.length) return;
    if (bulkAction !== "delete" && !bulkCourseId) return;
    bulkPendingRef.current = true;
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
    bulkPendingRef.current = false;
    setBulkPending(false);
    setBulkAction(null);
    setBulkCourseId(null);
  }

  function startDrag(event: DragEvent<HTMLElement>, record: InboxRecordOut) {
    const items = selectedIds.has(record.id) ? selectedRecords : [record];
    if (
      bulkPending ||
      items.some((item) => !ORGANIZABLE_STATUSES.has(item.status))
    ) {
      event.preventDefault();
      return;
    }
    const ids = items.map((item) => item.id);
    event.dataTransfer.setData(
      "application/x-knowrealm-inbox",
      JSON.stringify(ids),
    );
    event.dataTransfer.effectAllowed = "move";
    setDraggedIds(ids);
  }

  function classifyInto(courseId: string, ids?: string[]) {
    if (bulkPending || bulkAction) return;
    if (ids) setSelectedIds(new Set(ids));
    setBulkCourseId(courseId);
    setBulkAction("classify");
  }

  function dropInto(event: DragEvent<HTMLElement>, courseId: string) {
    event.preventDefault();
    const payload = event.dataTransfer.getData("application/x-knowrealm-inbox");
    const valid =
      draggedIds.length > 0 &&
      payload === JSON.stringify(draggedIds) &&
      draggedIds.every((id) =>
        allRecords.some(
          (record) =>
            record.id === id && ORGANIZABLE_STATUSES.has(record.status),
        ),
      );
    if (valid) classifyInto(courseId, draggedIds);
    else setFeedback(t("inbox.workspace.invalidDrop"));
    setDraggedIds([]);
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

  return (
    <section className="inbox-workspace max-w-workbench px-content mx-auto min-w-0">
      <div className="inbox-scroll-area min-h-0 flex-1 overflow-y-auto pt-6 pb-5">
        <InboxToolbar
          records={allRecords}
          search={search}
          onChange={updateSearch}
          onFilterChange={changeFilter}
        />
        {feedback ? (
          <p role="status" className="text-body text-muted-foreground mt-4">
            {feedback}
          </p>
        ) : null}

        <div
          className={`mt-4 grid min-h-0 gap-4 ${view === "list" ? "xl:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)]" : ""}`}
        >
          <div className="min-w-0">
            <div
              className={`${view === "desk" ? "hidden" : "inbox-list-columns"} text-muted-foreground grid-cols-[1rem_minmax(0,1fr)_5.5rem_7rem] items-center gap-3 px-4 py-3 text-xs 2xl:grid-cols-[1rem_minmax(0,1fr)_5.5rem_7rem_7rem_6rem]`}
            >
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
              <ul
                aria-label={t("inbox.listLabel")}
                className={
                  view === "desk" ? "inbox-grid" : "inbox-list min-w-0"
                }
              >
                {pageRecords.map((record) =>
                  view === "desk" ? (
                    <InboxCard
                      key={record.id}
                      record={record}
                      selected={record.id === selectedRecord?.id}
                      checked={selectedIds.has(record.id)}
                      disabled={bulkPending}
                      onCheckedChange={(checked) =>
                        toggleRecord(record.id, checked)
                      }
                      onPreview={() => openPreview(record.id)}
                      onClassified={(courseName) =>
                        setFeedback(
                          t("inbox.classifiedFeedback", { course: courseName }),
                        )
                      }
                      onDragStart={(event) => startDrag(event, record)}
                      onDragEnd={() => setDraggedIds([])}
                    />
                  ) : (
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
                      disabled={bulkPending}
                    />
                  ),
                )}
              </ul>
            ) : (
              <Empty className="items-start rounded-none px-2 py-10 text-start">
                <EmptyHeader className="items-start text-start">
                  {records.data.length === 0 ? (
                    <EmptyMedia className="text-muted-foreground">
                      <Inbox aria-hidden="true" className="size-5" />
                    </EmptyMedia>
                  ) : null}
                  <h2 className="text-section font-section text-ink">
                    {t(
                      records.data.length === 0
                        ? "inbox.emptyTitle"
                        : "inbox.noResultsTitle",
                    )}
                  </h2>
                  <EmptyDescription>
                    {t(
                      records.data.length === 0
                        ? "inbox.emptyDescription"
                        : "inbox.noResultsDescription",
                    )}
                  </EmptyDescription>
                </EmptyHeader>
                {records.data.length > 0 ? (
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
                ) : null}
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

          {view === "list" ? (
            <aside className="border-border bg-surface-raised sticky top-4 hidden max-h-[calc(100vh-var(--spacing-titlebar)-7rem)] min-h-[calc(100vh-var(--spacing-titlebar)-9.5rem)] min-w-0 self-start overflow-y-auto rounded-xl border xl:block">
              <InboxPreview
                record={selectedRecord}
                onClose={() => updateSearch({ record: undefined })}
                onClassified={(courseName) =>
                  setFeedback(
                    t("inbox.classifiedFeedback", { course: courseName }),
                  )
                }
              />
            </aside>
          ) : null}
        </div>
      </div>

      <InboxCourseTray
        dragging={draggedIds.length > 0}
        canClassify={allSelectedOrganizable}
        disabled={bulkPending || bulkAction !== null}
        onClassify={classifyInto}
        onDrop={dropInto}
      >
        <div className="flex min-h-9 flex-wrap items-center gap-3">
          <Checkbox
            checked={allPageSelected}
            indeterminate={!allPageSelected && selectedOnPage.length > 0}
            disabled={bulkPending}
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
                className="bg-surface-strong text-ink hover:bg-surface-subtle"
                disabled={bulkPending}
                onClick={() => setSelectedIds(new Set())}
              >
                {t("inbox.selection.clear")}
              </Button>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!allSelectedOrganizable || bulkPending}
                  onClick={() => setBulkAction("classify")}
                >
                  <FolderOpen aria-hidden="true" />
                  {t("inbox.bulk.classify")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!allSelectedOrganizable || bulkPending}
                  onClick={() => setBulkAction("upgrade")}
                >
                  <Rocket aria-hidden="true" />
                  {t("inbox.bulk.upgrade")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  disabled={bulkPending}
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
      </InboxCourseTray>

      <Dialog
        open={previewOpen && Boolean(selectedRecord)}
        onOpenChange={(open) => {
          setPreviewOpen(open);
          if (!open) updateSearch({ record: undefined });
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
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
  disabled,
}: {
  disabled: boolean;
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
      className={`inbox-row group border-border relative grid min-h-18 min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 border-b px-4 last:border-b-0 ${selected || checked ? "bg-inbox-soft" : "hover:bg-surface-subtle"}`}
    >
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-label={t("inbox.selection.record", { title })}
      />
      <button
        type="button"
        onClick={onPreview}
        className="focus-visible:ring-ring/40 grid min-w-0 grid-cols-1 items-center gap-3 py-3 text-left focus-visible:rounded-lg focus-visible:ring-3 focus-visible:outline-hidden md:grid-cols-[minmax(0,1fr)_5.5rem_7rem] 2xl:grid-cols-[minmax(0,1fr)_5.5rem_7rem_7rem_6rem]"
        aria-label={t("inbox.preview.action", { title })}
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="text-muted-foreground flex size-8 shrink-0 items-center justify-center">
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
      <div className="bg-surface-raised absolute right-3 flex items-center gap-1 rounded-lg pl-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
        <div>
          <InboxRowActions
            record={record}
            onClassified={onClassified}
            compact
            disabled={disabled}
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
