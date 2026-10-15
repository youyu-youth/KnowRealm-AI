import { useNavigate } from "@tanstack/react-router";
import {
  Archive,
  ArchiveRestore,
  BookOpen,
  Clock3,
  ChevronDown,
  FolderOpen,
  Search,
  SlidersHorizontal,
  X,
  ExternalLink,
  FileText,
  FolderSearch,
  Globe,
  Lightbulb,
  Mic,
  LayoutGrid,
  List as ListIcon,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  RefreshCw,
  Sparkles,
  Star,
  StickyNote,
  Trash2,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { LibraryCard } from "@/features/library/components/LibraryCard";
import "@/features/library/library.css";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { formatSize } from "@/lib/utils";
import {
  AddLibraryItemDialog,
  type AddLibraryItemInitial,
} from "@/features/library/components/AddLibraryItemDialog";
import { DeleteItemDialog } from "@/features/library/components/DeleteItemDialog";
import { EditItemDialog } from "@/features/library/components/EditItemDialog";
import { OrganizeDialog } from "@/features/library/components/OrganizeDialog";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";
import { revealLibrarySnapshot } from "@/services/tauri/libraryFiles";
import { openWebUrl } from "@/services/tauri/webLinks";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
  SheetClose,
} from "@/components/ui/sheet";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusTag, type StatusTagTone } from "@/components/common/StatusTag";
import { ToggleChip } from "@/components/common/ToggleChip";
import { useActiveCourses } from "@/features/courses/api/queries";
import {
  useLibraryAssets,
  useLibraryItemAction,
  type LibraryItemsParams,
  useLibraryItemContent,
  useLibraryItemDetail,
  useLibraryItems,
  useLibraryRecords,
  useToggleFavorite,
  type LibraryAssetOut,
  type LibraryItemOut,
  type LibraryRecordOut,
} from "@/features/library/api/library";
import type {
  LibraryDomain,
  LibrarySearch,
  LibrarySelType,
  LibrarySourceTypeFilter,
  LibraryView,
} from "@/features/library/librarySearch";

const PAGE_SIZE = 50;
const VISIBLE_COURSE_LIMIT = 6;

const domainValues: LibraryDomain[] = ["all", "sources", "records", "assets"];
const viewValues: LibraryView[] = [
  "all",
  "recent",
  "favorites",
  "needsReview",
  "archived",
  "trash",
];

const sourceTypeIcon: Record<string, LucideIcon> = {
  AUDIO: Mic,
  DOCUMENT: FileText,
  WEB: Globe,
  BOOK: BookOpen,
  TEXT: StickyNote,
};

const availabilityTone: Record<string, StatusTagTone> = {
  PROCESSING: "warning",
  RETRIEVABLE: "success",
  FAILED: "danger",
  EMPTY: "neutral",
};

const sourceTypeFilters: LibrarySourceTypeFilter[] = [
  "AUDIO",
  "DOCUMENT",
  "WEB",
  "TEXT",
];

const availabilityFilters = [
  "RETRIEVABLE",
  "PROCESSING",
  "FAILED",
  "EMPTY",
] as const;

const ROW_SHELL =
  "hover:bg-surface-subtle rounded-xl border border-solid transition-colors";
const ROW_SELECTED = "bg-surface-strong";

function captureSourceType(
  captureType: LibraryRecordOut["capture_type"],
): LibraryItemOut["source_type"] {
  return captureType === "RECORDING" || captureType === "AUDIO_IMPORT"
    ? "AUDIO"
    : captureType === "PASTE" || captureType === "QUICK_NOTE"
      ? "TEXT"
      : captureType === "CLIP"
        ? "WEB"
        : "DOCUMENT";
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function SourceTypeIcon({ sourceType }: { sourceType: string }) {
  const Icon = sourceTypeIcon[sourceType] ?? FileText;
  return <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />;
}

// ---------------------------------------------------------------------------
// 课程筛选：保留选中课程，其余超量课程收进菜单。

function SidebarNav({
  search,
  onSearchChange,
}: {
  search: LibrarySearch;
  onSearchChange: (next: LibrarySearch) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { courses } = useActiveCourses();
  const selectedCourse = courses.find(
    (course) => course.id === search.courseId,
  );
  const firstCourses = courses.slice(0, VISIBLE_COURSE_LIMIT);
  const visibleCourses =
    selectedCourse && !firstCourses.includes(selectedCourse)
      ? [...firstCourses.slice(0, VISIBLE_COURSE_LIMIT - 1), selectedCourse]
      : firstCourses;
  const hiddenCourses = courses.filter(
    (course) => !visibleCourses.includes(course),
  );
  const navItemClass =
    "focus-visible:ring-ring/40 flex w-full items-center gap-2 rounded-lg px-3 py-4 text-left text-body transition-colors hover:bg-surface-subtle focus-visible:ring-3 focus-visible:outline-hidden";
  const navItemActiveClass = "bg-surface-strong font-medium";

  const setPatch = (patch: LibrarySearch) =>
    onSearchChange({ ...search, ...patch });

  return (
    <nav
      aria-label={t("library.groups.courses")}
      className="library-course-nav"
    >
      <div className="mb-3 flex items-center justify-between gap-2 px-2">
        <p className="text-body font-semibold">{t("library.groups.courses")}</p>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label={t("library.groups.viewAllCourses")}
          onClick={() => void navigate({ to: "/spaces" })}
        >
          <Plus aria-hidden />
        </Button>
      </div>
      <button
        type="button"
        className={`${navItemClass} ${!search.courseId ? navItemActiveClass : ""}`}
        aria-current={!search.courseId ? "true" : undefined}
        onClick={() => setPatch({ courseId: undefined })}
      >
        <LayoutGrid className="size-6 shrink-0" aria-hidden />
        <span>{t("library.workspace.allCourses")}</span>
      </button>
      {visibleCourses.map((course) => (
        <button
          key={course.id}
          type="button"
          className={`${navItemClass} ${search.courseId === course.id ? navItemActiveClass : ""}`}
          aria-current={search.courseId === course.id ? "true" : undefined}
          title={course.name}
          onClick={() => setPatch({ courseId: course.id })}
        >
          <BookOpen className="size-6 shrink-0" aria-hidden />
          <span className="min-w-0 truncate">{course.name}</span>
        </button>
      ))}
      {hiddenCourses.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" className="library-more-courses" />}
          >
            {t("library.groups.moreCourses", { count: hiddenCourses.length })}
            <ChevronDown aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent className="max-h-64 max-w-72 overflow-y-auto">
            <DropdownMenuGroup>
              {hiddenCourses.map((course) => (
                <DropdownMenuItem
                  key={course.id}
                  title={course.name}
                  onClick={() => setPatch({ courseId: course.id })}
                >
                  <BookOpen aria-hidden />
                  <span className="truncate">{course.name}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {courses.length === 0 ? (
        <p className="text-muted-foreground px-2 py-3 text-sm">
          {t("library.groups.noCourses")}
        </p>
      ) : null}
      <Button
        variant="ghost"
        className="mt-2 w-full justify-start"
        onClick={() => void navigate({ to: "/spaces" })}
      >
        {t("library.groups.viewAllCourses")}
      </Button>
      <Button
        variant="outline"
        className="library-classify-link"
        onClick={() => void navigate({ to: "/inbox" })}
      >
        <FolderOpen className="size-7" aria-hidden />
        <span>{t("library.workspace.classify")}</span>
        <span className="text-muted-foreground text-label">
          {t("library.workspace.classifyHint")}
        </span>
      </Button>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// 列表行（列表视图）

function ItemRow({
  item,
  selected,
  onSelect,
  hideFavorite = false,
}: {
  item: LibraryItemOut;
  selected: boolean;
  onSelect: () => void;
  hideFavorite?: boolean;
}) {
  const { t } = useTranslation();
  const toggleFavorite = useToggleFavorite();
  const meta = [
    item.deleted_at
      ? t("library.inspector.deletedAt", {
          time: formatDateTime(item.deleted_at),
        })
      : null,
    item.course_name ?? t("library.filters.unclassified"),
    t(`library.sourceTypes.${item.source_type}`),
    formatSize(item.file_size),
    formatDateTime(item.updated_at),
  ].filter(Boolean);
  return (
    <li className={`${ROW_SHELL} group`}>
      <div
        className={`flex min-h-[64px] grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-3 py-2 ${selected ? ROW_SELECTED : ""}`}
      >
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-pressed={selected}
        >
          <SourceTypeIcon sourceType={item.source_type} />
          <span className="min-w-0 flex-1">
            <span className="text-body block truncate font-medium">
              {item.title}
            </span>
            <span className="text-muted-foreground text-label block truncate">
              {meta.join(" · ")}
            </span>
          </span>
        </button>
        <StatusTag tone={availabilityTone[item.availability] ?? "neutral"}>
          {t(`library.availability.${item.availability}`)}
        </StatusTag>
        {hideFavorite ? null : (
          <Button
            variant="ghost"
            size="icon-sm"
            className={
              item.favorite
                ? "opacity-100"
                : "opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
            }
            aria-label={t("library.favoriteToggle")}
            aria-pressed={item.favorite}
            disabled={toggleFavorite.isPending}
            onClick={() =>
              toggleFavorite.mutate({
                itemId: item.id,
                favorite: !item.favorite,
              })
            }
          >
            <Star
              className={
                item.favorite
                  ? "text-ink fill-current"
                  : "text-muted-foreground"
              }
            />
          </Button>
        )}
      </div>
    </li>
  );
}

function RecordRow({
  record,
  selected,
  onSelect,
}: {
  record: LibraryRecordOut;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <li className="rounded-xl border border-solid">
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={`hover:bg-surface-subtle flex min-h-[64px] w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors ${selected ? "bg-surface-strong" : ""}`}
      >
        <SourceTypeIcon
          sourceType={
            record.capture_type === "RECORDING" ||
            record.capture_type === "AUDIO_IMPORT"
              ? "AUDIO"
              : "DOCUMENT"
          }
        />
        <span className="min-w-0 flex-1">
          <span className="text-body block truncate font-medium">
            {record.title}
          </span>
          <span className="text-muted-foreground text-label block truncate">
            {[
              record.course_name ?? t("library.filters.unclassified"),
              t(`spaces.records.status.${record.status}`),
              formatDateTime(record.updated_at),
            ].join(" · ")}
          </span>
        </span>
      </button>
    </li>
  );
}

function AssetRow({
  asset,
  selected,
  onSelect,
}: {
  asset: LibraryAssetOut;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <li className="rounded-xl border border-solid">
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={`hover:bg-surface-subtle flex min-h-[64px] w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors ${selected ? "bg-surface-strong" : ""}`}
      >
        <Lightbulb
          className="text-muted-foreground size-4 shrink-0"
          aria-hidden
        />
        <span className="min-w-0 flex-1">
          <span className="text-body block truncate font-medium">
            {asset.name}
          </span>
          <span className="text-muted-foreground text-label block truncate">
            {[
              asset.record_title,
              asset.course_name ?? t("library.filters.unclassified"),
              formatDateTime(asset.updated_at),
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </span>
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// 检查器

function MetaRow({ label, value }: { label: string; value: string | null }) {
  if (value === null || value === "") return null;
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="text-muted-foreground text-label shrink-0">{label}</dt>
      <dd className="text-label text-right break-all">{value}</dd>
    </div>
  );
}

function ItemInspector({
  itemId,
  onManualPaste,
  onReingest,
}: {
  itemId: string;
  onManualPaste: (item: { origin_uri: string | null; title: string }) => void;
  onReingest: (item: { origin_uri: string | null; title: string }) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const detail = useLibraryItemDetail(itemId);
  const content = useLibraryItemContent(itemId);
  const item = detail.data;
  // 「AI 解读」（工单 04）：对该资料创建 LIBRARY_ITEM 会话并跳转对话页。
  const createChatSession = useCreateChatSession();
  const interpret = () =>
    createChatSession.mutate({
      mode: "ASK",
      scope: "LIBRARY_ITEM",
      library_item_id: itemId,
    });
  // 生命周期动作（工单 05）：编辑/归档切换/删除/重试/重抓/重建索引/回收站恢复。
  const lifecycle = useLibraryItemAction();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const runLifecycle = (
    action: Parameters<typeof lifecycle.mutate>[0]["action"],
  ) => {
    setActionError(null);
    setActionNotice(null);
    lifecycle.mutate(
      { action, itemId },
      {
        onError: (error) => setActionError(error.message),
        onSuccess: () => {
          if (action === "refetch") {
            setActionNotice(t("library.inspector.refetchDone"));
          }
        },
      },
    );
  };
  if (detail.isPending) {
    return (
      <div className="text-muted-foreground flex items-center gap-2 py-6 text-sm">
        <Spinner className="size-4" /> {t("library.inspector.loading")}
      </div>
    );
  }
  if (detail.isError || item === undefined) {
    return (
      <p className="text-muted-foreground py-6 text-sm">
        {t("library.inspector.itemError")}
      </p>
    );
  }
  // 宽松判空：历史 mock/载荷无该字段时视为未删除。
  const inTrash = item.deleted_at != null;
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <SourceTypeIcon sourceType={item.source_type} />
        <div className="min-w-0 flex-1">
          <p className="text-body font-medium break-words">{item.title}</p>
          <p className="text-muted-foreground text-label">
            {t(`library.sourceTypes.${item.source_type}`)} ·{" "}
            {item.course_name ?? t("library.filters.unclassified")}
            {inTrash
              ? ` · ${t("library.inspector.deletedAt", {
                  time: formatDateTime(item.deleted_at ?? ""),
                })}`
              : ""}
          </p>
        </div>
        <StatusTag tone={availabilityTone[item.availability] ?? "neutral"}>
          {t(`library.availability.${item.availability}`)}
        </StatusTag>
      </div>

      {inTrash ? (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => runLifecycle("restore")}
              disabled={lifecycle.isPending}
            >
              <ArchiveRestore className="size-4" aria-hidden />
              {t("library.inspector.restore")}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
              disabled={lifecycle.isPending}
            >
              <Trash2 className="size-4" aria-hidden />
              {t("library.inspector.purge")}
            </Button>
          </div>
          <p className="text-muted-foreground text-label">
            {t("library.inspector.trashHint")}
          </p>
        </div>
      ) : (
        <>
          <div>
            <Button
              size="sm"
              onClick={interpret}
              disabled={
                createChatSession.isPending || item.status === "ARCHIVED"
              }
              title={
                item.status === "ARCHIVED"
                  ? t("library.inspector.aiInterpretUnavailable")
                  : undefined
              }
            >
              <Sparkles className="size-4" aria-hidden />
              {createChatSession.isPending
                ? t("library.inspector.aiInterpretPending")
                : t("library.inspector.aiInterpret")}
            </Button>
            {createChatSession.isError ? (
              <p role="alert" className="text-destructive text-label mt-1">
                {createChatSession.error.message}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditOpen(true)}
            >
              <Pencil className="size-4" aria-hidden />
              {t("library.inspector.edit")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                runLifecycle(
                  item.status === "ARCHIVED" ? "unarchive" : "archive",
                )
              }
              disabled={lifecycle.isPending}
            >
              {item.status === "ARCHIVED" ? (
                <ArchiveRestore className="size-4" aria-hidden />
              ) : (
                <Archive className="size-4" aria-hidden />
              )}
              {item.status === "ARCHIVED"
                ? t("library.inspector.unarchive")
                : t("library.inspector.archive")}
            </Button>
            {item.source_type === "WEB" ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => runLifecycle("refetch")}
                disabled={lifecycle.isPending}
                title={t("library.inspector.refetchHint")}
              >
                <RefreshCw className="size-4" aria-hidden />
                {t("library.inspector.refetch")}
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              onClick={() => runLifecycle("rebuild-index")}
              disabled={lifecycle.isPending}
            >
              <Wrench className="size-4" aria-hidden />
              {t("library.inspector.rebuildIndex")}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
              disabled={lifecycle.isPending}
            >
              <Trash2 className="size-4" aria-hidden />
              {t("library.inspector.delete")}
            </Button>
          </div>
        </>
      )}

      {actionNotice ? (
        <p className="text-label text-muted-foreground" role="status">
          {actionNotice}
        </p>
      ) : null}
      {actionError || lifecycle.isError ? (
        <p role="alert" className="text-destructive text-label">
          {actionError ?? lifecycle.error?.message}
        </p>
      ) : null}

      {item.availability === "FAILED" ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            {/* 只有抓取域专属错误码有面向任务的文案；INTERNAL_ERROR 等通用码
                复用 HTTP 500 文案（含请求编号插值）会误导为请求失败 */}
            {item.failed_error_code?.startsWith("WEB_FETCH_")
              ? t(`errors.${item.failed_error_code}`)
              : t("library.inspector.failedHint")}
          </AlertDescription>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => runLifecycle("retry")}
              disabled={lifecycle.isPending}
            >
              <RotateCcw className="size-4" aria-hidden />
              {t("library.inspector.retry")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onReingest(item)}
              disabled={item.source_type !== "WEB"}
            >
              {t("library.inspector.reingest")}
            </Button>
            {item.source_type === "WEB" ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onManualPaste(item)}
              >
                {t("library.inspector.manualPaste")}
              </Button>
            ) : null}
          </div>
        </Alert>
      ) : null}

      {editOpen ? (
        <EditItemDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          item={item}
        />
      ) : null}
      {deleteOpen ? (
        <DeleteItemDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          item={item}
          permanent={inTrash}
        />
      ) : null}

      {item.origin_uri || item.local_path ? (
        <div className="flex flex-wrap gap-2">
          {item.origin_uri ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void openWebUrl(item.origin_uri ?? "")}
            >
              <ExternalLink className="size-4" aria-hidden />
              {t("library.inspector.openOrigin")}
            </Button>
          ) : null}
          {item.local_path ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void revealLibrarySnapshot(item.local_path ?? "")}
            >
              <FolderSearch className="size-4" aria-hidden />
              {t("library.inspector.revealFile")}
            </Button>
          ) : null}
        </div>
      ) : null}

      <section>
        <h4 className="text-label text-muted-foreground font-label mb-1">
          {t("library.inspector.sourceMeta")}
        </h4>
        <dl className="divide-y">
          <MetaRow
            label={t("library.inspector.originUri")}
            value={item.origin_uri}
          />
          <MetaRow
            label={t("library.inspector.localPath")}
            value={item.local_path}
          />
          <MetaRow label={t("library.inspector.mime")} value={item.mime_type} />
          <MetaRow
            label={t("library.inspector.size")}
            value={formatSize(item.file_size)}
          />
          <MetaRow
            label={t("library.inspector.segmentCount")}
            value={String(item.segment_count)}
          />
          <MetaRow
            label={t("library.inspector.updated")}
            value={formatDateTime(item.updated_at)}
          />
        </dl>
      </section>

      {item.derived_records.length > 0 ? (
        <section>
          <h4 className="text-label text-muted-foreground font-label mb-1">
            {t("library.inspector.derivedRecords")}
          </h4>
          <ul className="space-y-1">
            {item.derived_records.map((record) => (
              <li key={record.record_id}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full justify-start truncate"
                  onClick={() =>
                    void navigate({
                      to: "/records/$recordId",
                      params: { recordId: record.record_id },
                    })
                  }
                >
                  {record.title}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h4 className="text-label text-muted-foreground font-label mb-1">
          {t("library.inspector.preview")}
        </h4>
        {content.isPending ? (
          <div className="text-muted-foreground flex items-center gap-2 text-sm">
            <Spinner className="size-4" />
          </div>
        ) : content.isError || !content.data ? (
          <p className="text-muted-foreground text-sm">
            {t("library.inspector.previewEmpty")}
          </p>
        ) : (
          <>
            <pre className="bg-surface-subtle max-h-56 overflow-y-auto rounded-lg p-3 text-sm break-words whitespace-pre-wrap">
              {content.data.content}
            </pre>
            {content.data.truncated ? (
              <p className="text-muted-foreground text-label mt-1">
                {t("library.inspector.previewTruncated")}
              </p>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

function RecordInspector({
  record,
  items,
}: {
  record: LibraryRecordOut;
  items: LibraryItemOut[];
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const sourceItems = items.filter((item) =>
    record.library_item_ids.includes(item.id),
  );
  return (
    <div className="space-y-4">
      <div>
        <p className="text-body font-medium break-words">{record.title}</p>
        <p className="text-muted-foreground text-label">
          {record.course_name ?? t("library.filters.unclassified")} ·{" "}
          {t(`spaces.records.status.${record.status}`)}
        </p>
      </div>
      <section>
        <h4 className="text-label text-muted-foreground font-label mb-1">
          {t("library.inspector.recordSources")}
        </h4>
        {sourceItems.length > 0 ? (
          <ul className="space-y-1">
            {sourceItems.map((item) => (
              <li
                key={item.id}
                className="text-label flex items-center gap-2 py-1"
              >
                <SourceTypeIcon sourceType={item.source_type} />
                <span className="truncate">{item.title}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">
            {t("library.inspector.noSources")}
          </p>
        )}
      </section>
      <section>
        <h4 className="text-label text-muted-foreground font-label mb-1">
          {t("library.inspector.recordAssets")}
        </h4>
        <p className="text-muted-foreground mb-2 text-sm">
          {t("library.inspector.recordAssetsHint")}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            void navigate({
              to: "/records/$recordId",
              params: { recordId: record.id },
            })
          }
        >
          {t("library.inspector.openRecord")}
        </Button>
      </section>
    </div>
  );
}

function AssetInspector({ asset }: { asset: LibraryAssetOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <Lightbulb
          className="text-muted-foreground mt-0.5 size-4 shrink-0"
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-body font-medium break-words">{asset.name}</p>
          <p className="text-muted-foreground text-label">
            {t("library.inspector.importance")}: {asset.importance.toFixed(1)}
          </p>
        </div>
      </div>
      {asset.detail ? (
        <p className="text-sm break-words whitespace-pre-wrap">
          {asset.detail}
        </p>
      ) : null}
      <section>
        <h4 className="text-label text-muted-foreground font-label mb-1">
          {t("library.inspector.assetRecord")}
        </h4>
        {asset.record_title ? (
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start truncate"
            onClick={() =>
              void navigate({
                to: "/records/$recordId",
                params: { recordId: asset.record_id },
              })
            }
          >
            {asset.record_title}
          </Button>
        ) : null}
      </section>
    </div>
  );
}

function Inspector({
  search,
  items,
  records,
  assets,
  onManualPaste,
  onReingest,
}: {
  search: LibrarySearch;
  items: LibraryItemOut[];
  records: LibraryRecordOut[];
  assets: LibraryAssetOut[];
  onManualPaste: (item: { origin_uri: string | null; title: string }) => void;
  onReingest: (item: { origin_uri: string | null; title: string }) => void;
}) {
  const { t } = useTranslation();
  if (!search.sel || !search.selType) {
    return (
      <p className="text-muted-foreground py-6 text-sm">
        {t("library.inspector.noneSelected")}
      </p>
    );
  }
  if (search.selType === "item") {
    return (
      <ItemInspector
        key={search.sel}
        itemId={search.sel}
        onManualPaste={onManualPaste}
        onReingest={onReingest}
      />
    );
  }
  if (search.selType === "record") {
    const record = records.find((row) => row.id === search.sel);
    if (record === undefined) {
      return (
        <p className="text-muted-foreground py-6 text-sm">
          {t("library.inspector.notFound")}
        </p>
      );
    }
    return <RecordInspector record={record} items={items} />;
  }
  const asset = assets.find((row) => row.id === search.sel);
  if (asset === undefined) {
    return (
      <p className="text-muted-foreground py-6 text-sm">
        {t("library.inspector.notFound")}
      </p>
    );
  }
  return <AssetInspector asset={asset} />;
}

// ---------------------------------------------------------------------------
// 主页面

export function LibraryPage({
  search,
  onSearchChange,
}: {
  search: LibrarySearch;
  onSearchChange: (next: LibrarySearch) => void;
}) {
  const { t } = useTranslation();
  const [inspectorOpen, setInspectorOpen] = useState(
    Boolean(search.sel && search.selType),
  );
  const [ingestOpen, setIngestOpen] = useState(false);
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [ingestInitial, setIngestInitial] = useState<
    AddLibraryItemInitial | undefined
  >(undefined);
  const domain = search.domain ?? "all";
  const view = search.view ?? "all";
  const layout = search.layout ?? "grid";
  const { courses } = useActiveCourses();

  const itemsParams = useMemo<LibraryItemsParams>(
    () => ({
      view,
      sourceType: search.sourceType,
      availability: search.availability,
      courseId: search.courseId,
      q: search.q?.trim() || undefined,
      limit: PAGE_SIZE,
    }),
    [view, search.sourceType, search.availability, search.courseId, search.q],
  );
  // 「解析中」条目存在时轮询可用性派生，终态即停（无无限 spinner）。
  const itemsQuery = useLibraryItems(
    domain === "all" || domain === "sources" ? itemsParams : { limit: 1 },
    {
      refetchIntervalMs: (data) =>
        (data?.items ?? []).some((item) => item.availability === "PROCESSING")
          ? 2000
          : false,
    },
  );
  const recordsQuery = useLibraryRecords();
  const assetsQuery = useLibraryAssets();

  const allItems = useMemo(
    () => itemsQuery.data?.items ?? [],
    [itemsQuery.data],
  );

  const allRecords = useMemo(
    () => recordsQuery.data ?? [],
    [recordsQuery.data],
  );
  const allAssets = useMemo(() => assetsQuery.data ?? [], [assetsQuery.data]);

  // 联邦「全部」：三类对象按更新时间合并；单一域时只取该域。
  const filteredRecords = useMemo(() => {
    if (domain === "sources" || domain === "assets") return [];
    return allRecords.filter(
      (record) =>
        (search.courseId ? record.course_id === search.courseId : true) &&
        (search.q?.trim() ? record.title.includes(search.q.trim()) : true),
    );
  }, [domain, allRecords, search.courseId, search.q]);
  const filteredAssets = useMemo(() => {
    if (domain === "sources" || domain === "records") return [];
    return allAssets.filter(
      (asset) =>
        (search.courseId ? asset.course_id === search.courseId : true) &&
        (search.q?.trim() ? asset.name.includes(search.q.trim()) : true),
    );
  }, [domain, allAssets, search.courseId, search.q]);

  const select = (selType: LibrarySelType, id: string) => {
    onSearchChange({ ...search, sel: id, selType });
    setInspectorOpen(true);
  };

  const backfill = itemsQuery.data?.backfill;
  const backfillActive =
    backfill !== null &&
    backfill !== undefined &&
    (backfill.status === "PENDING" || backfill.status === "RUNNING");
  const backfillFailed =
    backfill !== null && backfill !== undefined && backfill.status === "FAILED";

  const isListPending =
    ((domain === "sources" || domain === "all") && itemsQuery.isPending) ||
    ((domain === "records" || domain === "all") && recordsQuery.isPending) ||
    ((domain === "assets" || domain === "all") && assetsQuery.isPending);
  const failedQueries = [
    ...(domain === "sources" || domain === "all" ? [itemsQuery] : []),
    ...(domain === "records" || domain === "all" ? [recordsQuery] : []),
    ...(domain === "assets" || domain === "all" ? [assetsQuery] : []),
  ].filter((query) => query.isError);
  const isEmptyList =
    domain === "sources"
      ? allItems.length === 0
      : domain === "records"
        ? filteredRecords.length === 0
        : domain === "assets"
          ? filteredAssets.length === 0
          : allItems.length + filteredRecords.length + filteredAssets.length ===
            0;

  const openIngestDialog = (initial?: AddLibraryItemInitial) => {
    setIngestInitial(initial);
    setIngestOpen(true);
  };
  const openExistingItem = (itemId: string) => {
    onSearchChange({ ...search, sel: itemId, selType: "item" });
    setInspectorOpen(true);
  };
  const inspectorBody = (
    <Inspector
      search={search}
      items={allItems}
      records={allRecords}
      assets={allAssets}
      onManualPaste={(item) =>
        openIngestDialog({
          tab: "text",
          originUri: item.origin_uri ?? undefined,
          title: item.title,
        })
      }
      onReingest={(item) =>
        openIngestDialog({
          tab: "web",
          url: item.origin_uri ?? undefined,
        })
      }
    />
  );

  return (
    <section className="library-workspace">
      <aside className="library-course-sidebar">
        <SidebarNav search={search} onSearchChange={onSearchChange} />
      </aside>
      <div className="library-main">
        <header className="library-header">
          <div className="min-w-0">
            <h1 className="text-library-title text-ink-strong font-semibold">
              {t("library.title")}
            </h1>
            <p className="text-muted-foreground text-body mt-1">
              {t("library.description")}
            </p>
          </div>
          <div className="library-header-actions">
            <div className="library-search">
              <Search
                className="text-library-muted size-4 shrink-0"
                aria-hidden
              />
              <Input
                value={search.q ?? ""}
                onChange={(event) =>
                  onSearchChange({ ...search, q: event.target.value })
                }
                placeholder={t("library.filters.searchPlaceholder")}
                aria-label={t("library.filters.searchLabel")}
              />
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="outline" size="sm" />}
              >
                <SlidersHorizontal aria-hidden />
                {t("library.workspace.filters")}
                {search.availability ? (
                  <span className="size-1.5 rounded-full bg-current" />
                ) : null}
                <ChevronDown aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>
                    {t("library.workspace.availability")}
                  </DropdownMenuLabel>
                  {availabilityFilters.map((state) => (
                    <DropdownMenuCheckboxItem
                      key={state}
                      checked={search.availability === state}
                      disabled={domain === "records" || domain === "assets"}
                      onCheckedChange={() =>
                        onSearchChange({
                          ...search,
                          availability:
                            search.availability === state ? undefined : state,
                        })
                      }
                    >
                      {t(`library.availability.${state}`)}
                    </DropdownMenuCheckboxItem>
                  ))}
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button onClick={() => openIngestDialog()}>
              <Plus aria-hidden />
              {t("library.ingest.open")}
            </Button>
            <Button variant="outline" onClick={() => setOrganizeOpen(true)}>
              <Sparkles aria-hidden />
              {t("library.organize.open")}
            </Button>
          </div>
        </header>
        <div className="library-viewbar">
          <Tabs
            value={domain}
            onValueChange={(next) =>
              onSearchChange({
                ...search,
                domain:
                  next === "all"
                    ? undefined
                    : (next as Exclude<LibraryDomain, "all">),
              })
            }
          >
            <TabsList variant="line" className="library-domain-tabs">
              {domainValues.map((tabDomain) => (
                <TabsTrigger key={tabDomain} value={tabDomain}>
                  {t(`library.domains.${tabDomain}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div
            className="library-smart-views"
            role="group"
            aria-label={t("library.groups.smart")}
          >
            {viewValues
              .filter((value) => value !== "all")
              .map((chipView) => {
                const Icon = {
                  all: LayoutGrid,
                  recent: Clock3,
                  favorites: Star,
                  needsReview: Wrench,
                  archived: Archive,
                  trash: Trash2,
                }[chipView];
                return (
                  <ToggleChip
                    key={chipView}
                    active={view === chipView}
                    onClick={() =>
                      onSearchChange({
                        ...search,
                        view: view === chipView ? undefined : chipView,
                      })
                    }
                  >
                    <Icon className="size-4" aria-hidden />
                    {t(`library.views.${chipView}`)}
                  </ToggleChip>
                );
              })}
          </div>
        </div>
        <div className="library-content-toolbar">
          <div className="flex min-w-0 items-center gap-3">
            <LayoutGrid
              className="text-library-ink size-6 shrink-0"
              aria-hidden
            />
            <h2 className="text-library-heading text-ink-strong min-w-0 font-semibold break-words">
              {courses.find((course) => course.id === search.courseId)?.name ??
                (search.courseId
                  ? t("library.filters.courseFilterActive")
                  : t("library.workspace.allCourses"))}
            </h2>
            <span className="text-library-muted text-body shrink-0">
              {t("library.workspace.visibleCount", {
                count:
                  (domain === "all" || domain === "sources"
                    ? allItems.length
                    : 0) +
                  filteredRecords.length +
                  filteredAssets.length,
              })}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {domain !== "records" && domain !== "assets" ? (
              <div
                className="library-type-filters"
                role="group"
                aria-label={t("library.workspace.types")}
              >
                <ToggleChip
                  active={!search.sourceType}
                  onClick={() =>
                    onSearchChange({ ...search, sourceType: undefined })
                  }
                >
                  {t("library.workspace.allTypes")}
                </ToggleChip>
                {sourceTypeFilters.map((type) => {
                  const Icon = sourceTypeIcon[type] ?? FileText;
                  return (
                    <ToggleChip
                      key={type}
                      active={search.sourceType === type}
                      onClick={() =>
                        onSearchChange({
                          ...search,
                          sourceType:
                            search.sourceType === type ? undefined : type,
                        })
                      }
                    >
                      <Icon className="size-4" aria-hidden />
                      {t(`library.sourceTypes.${type}`)}
                    </ToggleChip>
                  );
                })}
              </div>
            ) : null}
            <div
              className="flex items-center gap-1"
              role="group"
              aria-label={t("library.workspace.layout")}
            >
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("library.layout.list")}
                aria-pressed={layout === "list"}
                onClick={() => onSearchChange({ ...search, layout: "list" })}
              >
                <ListIcon aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("library.layout.grid")}
                aria-pressed={layout === "grid"}
                onClick={() => onSearchChange({ ...search, layout: "grid" })}
              >
                <LayoutGrid aria-hidden />
              </Button>
            </div>
          </div>
        </div>
        <div className="library-mobile-courses">
          <SidebarNav search={search} onSearchChange={onSearchChange} />
        </div>
        {search.availability || search.courseId ? (
          <div className="mb-3 flex flex-wrap gap-2">
            {search.availability ? (
              <ToggleChip
                active
                onClick={() =>
                  onSearchChange({ ...search, availability: undefined })
                }
              >
                {t(`library.availability.${search.availability}`)}
                <X className="ml-1 inline size-3" aria-hidden />
              </ToggleChip>
            ) : null}
            {search.courseId ? (
              <ToggleChip
                active
                onClick={() =>
                  onSearchChange({ ...search, courseId: undefined })
                }
              >
                {t("library.filters.courseFilterActive")}
                <X className="ml-1 inline size-3" aria-hidden />
              </ToggleChip>
            ) : null}
          </div>
        ) : null}
        {backfillFailed ? (
          <div
            className="border-danger text-muted-foreground bg-surface-raised flex items-center gap-2 rounded-lg border border-solid px-3 py-1.5 text-sm"
            role="alert"
          >
            {t("library.backfill.failed")}
          </div>
        ) : null}
        {backfillActive && backfill ? (
          <div
            className="bg-surface-raised flex items-center gap-2 rounded-lg border border-solid px-3 py-1.5 text-sm"
            role="status"
          >
            <Loader2
              className="text-muted-foreground size-4 animate-spin"
              aria-hidden
            />
            {t("library.backfill.running", {
              percent: Math.round(backfill.progress * 100),
            })}
          </div>
        ) : null}

        {failedQueries.length ? (
          <Alert variant="destructive" className="mb-3">
            <AlertDescription>
              {t("library.workspace.loadError")}
            </AlertDescription>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                failedQueries.forEach((query) => void query.refetch())
              }
            >
              {t("library.workspace.retry")}
            </Button>
          </Alert>
        ) : null}
        <div className="library-results">
          <div className="min-w-0">
            {view === "trash" ? (
              <Alert className="mb-3">
                <AlertDescription>{t("library.trash.banner")}</AlertDescription>
              </Alert>
            ) : null}
            {isListPending ? (
              <div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
                <Spinner className="size-4" /> {t("library.loading")}
              </div>
            ) : isEmptyList && failedQueries.length === 0 ? (
              <Empty className="border-t border-solid bg-transparent px-0 py-8">
                <EmptyHeader className="max-w-reading text-left">
                  <EmptyMedia className="text-muted-foreground">
                    <Star className="size-5" aria-hidden />
                  </EmptyMedia>
                  <EmptyTitle className="text-section font-section text-ink">
                    {search.q?.trim()
                      ? t("library.list.noResults")
                      : t("library.list.emptyTitle")}
                  </EmptyTitle>
                  <EmptyDescription className="max-w-reading text-body">
                    {search.q?.trim()
                      ? t("library.list.noResultsDescription")
                      : t("library.list.emptyDescription")}
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : layout === "grid" ? (
              <ul
                className="library-masonry"
                aria-label={t("library.layout.grid")}
              >
                {domain === "sources" || domain === "all"
                  ? allItems.map((item) => (
                      <li key={item.id}>
                        <LibraryCard
                          entry={{
                            id: item.id,
                            sourceType: item.source_type,
                            title: item.title,
                            updatedAt: item.updated_at,
                            courseName: item.course_name,
                            item,
                          }}
                          selected={
                            search.selType === "item" && search.sel === item.id
                          }
                          onSelect={() => select("item", item.id)}
                        />
                      </li>
                    ))
                  : null}
                {domain === "records" || domain === "all"
                  ? filteredRecords.map((record) => (
                      <li key={record.id}>
                        <LibraryCard
                          entry={{
                            id: record.id,
                            sourceType: captureSourceType(record.capture_type),
                            title: record.title,
                            updatedAt: record.updated_at,
                            courseName: record.course_name,
                            durationMs: record.duration_ms,
                            status: t(`spaces.records.status.${record.status}`),
                          }}
                          selected={
                            search.selType === "record" &&
                            search.sel === record.id
                          }
                          onSelect={() => select("record", record.id)}
                        />
                      </li>
                    ))
                  : null}
                {domain === "assets" || domain === "all"
                  ? filteredAssets.map((asset) => (
                      <li key={asset.id}>
                        <LibraryCard
                          entry={{
                            id: asset.id,
                            sourceType: "ASSET",
                            title: asset.name,
                            updatedAt: asset.updated_at,
                            courseName: asset.course_name,
                            detail: asset.detail,
                          }}
                          selected={
                            search.selType === "asset" &&
                            search.sel === asset.id
                          }
                          onSelect={() => select("asset", asset.id)}
                        />
                      </li>
                    ))
                  : null}
              </ul>
            ) : (
              <ul className="space-y-2">
                {domain === "sources" || domain === "all"
                  ? allItems.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        selected={
                          search.selType === "item" && search.sel === item.id
                        }
                        onSelect={() => select("item", item.id)}
                        hideFavorite={view === "trash"}
                      />
                    ))
                  : null}
                {domain === "records" || domain === "all"
                  ? filteredRecords.map((record) => (
                      <RecordRow
                        key={record.id}
                        record={record}
                        selected={
                          search.selType === "record" &&
                          search.sel === record.id
                        }
                        onSelect={() => select("record", record.id)}
                      />
                    ))
                  : null}
                {domain === "assets" || domain === "all"
                  ? filteredAssets.map((asset) => (
                      <AssetRow
                        key={asset.id}
                        asset={asset}
                        selected={
                          search.selType === "asset" && search.sel === asset.id
                        }
                        onSelect={() => select("asset", asset.id)}
                      />
                    ))
                  : null}
              </ul>
            )}
          </div>
        </div>
      </div>
      <Sheet
        open={inspectorOpen}
        onOpenChange={setInspectorOpen}
        onOpenChangeComplete={(open) => {
          if (!open)
            onSearchChange({ ...search, sel: undefined, selType: undefined });
        }}
      >
        <SheetContent className="library-preview-sheet" showCloseButton={false}>
          <SheetHeader className="flex-row items-center justify-between gap-3 border-b">
            <div>
              <SheetTitle>{t("library.inspector.title")}</SheetTitle>
              <SheetDescription className="sr-only">
                {t("library.description")}
              </SheetDescription>
            </div>
            <SheetClose
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("library.workspace.close")}
                />
              }
            >
              <X aria-hidden />
            </SheetClose>
          </SheetHeader>
          <SheetBody>{inspectorBody}</SheetBody>
        </SheetContent>
      </Sheet>

      <AddLibraryItemDialog
        open={ingestOpen}
        onOpenChange={setIngestOpen}
        initial={ingestInitial}
        onOpenItem={openExistingItem}
      />

      <OrganizeDialog open={organizeOpen} onOpenChange={setOrganizeOpen} />
    </section>
  );
}
