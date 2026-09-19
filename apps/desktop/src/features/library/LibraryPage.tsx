import { useNavigate } from "@tanstack/react-router";
import {
  BookOpen,
  FileText,
  Globe,
  Lightbulb,
  Mic,
  LayoutGrid,
  List as ListIcon,
  Loader2,
  Star,
  StickyNote,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

const domainValues: LibraryDomain[] = ["all", "sources", "records", "assets"];
const viewValues: LibraryView[] = ["all", "recent", "favorites", "needsReview"];

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

function captureSourceType(captureType: string): string {
  return captureType === "RECORDING" || captureType === "AUDIO_IMPORT"
    ? "AUDIO"
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

function formatSize(bytes: number | null): string | null {
  if (bytes === null) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function SourceTypeIcon({ sourceType }: { sourceType: string }) {
  const Icon = sourceTypeIcon[sourceType] ?? FileText;
  return <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />;
}

// ---------------------------------------------------------------------------
// 左侧导航：智能视图 / 领域分类 / 最近 Course（仅筛选器，不展开树）

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
  const navItemClass =
    "focus-visible:ring-ring/40 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-body transition-colors hover:bg-surface-subtle focus-visible:ring-3 focus-visible:outline-hidden";
  const navItemActiveClass = "bg-surface-strong font-medium";

  const setPatch = (patch: LibrarySearch) =>
    onSearchChange({ ...search, ...patch });

  return (
    <nav aria-label={t("library.title")} className="space-y-5">
      <div>
        <p className="text-label text-muted-foreground font-label mb-1 px-2">
          {t("library.groups.smart")}
        </p>
        {viewValues.map((view) => (
          <button
            key={view}
            type="button"
            onClick={() =>
              setPatch({ view: view === "all" ? undefined : view })
            }
            className={`${navItemClass} ${(search.view ?? "all") === view ? navItemActiveClass : ""}`}
            aria-current={(search.view ?? "all") === view ? "true" : undefined}
          >
            {t(`library.views.${view}`)}
          </button>
        ))}
      </div>
      <div>
        <p className="text-label text-muted-foreground font-label mb-1 px-2">
          {t("library.groups.domain")}
        </p>
        {/* 「全部」由顶部四分类承载，左侧领域分类只列三个具体域（票面口径） */}
        {domainValues
          .filter((domain) => domain !== "all")
          .map((domain) => (
            <button
              key={domain}
              type="button"
              onClick={() => setPatch({ domain })}
              className={`${navItemClass} ${search.domain === domain ? navItemActiveClass : ""}`}
              aria-current={search.domain === domain ? "true" : undefined}
            >
              {t(`library.domains.${domain}`)}
            </button>
          ))}
      </div>
      <div>
        <p className="text-label text-muted-foreground font-label mb-1 px-2">
          {t("library.groups.courses")}
        </p>
        <div className="max-h-48 overflow-y-auto">
          {courses.slice(0, 6).map((course) => (
            <button
              key={course.id}
              type="button"
              onClick={() =>
                setPatch(
                  search.courseId === course.id
                    ? { courseId: undefined }
                    : { courseId: course.id },
                )
              }
              className={`${navItemClass} truncate ${search.courseId === course.id ? navItemActiveClass : ""}`}
              aria-current={search.courseId === course.id ? "true" : undefined}
            >
              {course.name}
            </button>
          ))}
          <button
            type="button"
            onClick={() => void navigate({ to: "/spaces" })}
            className={`${navItemClass} text-muted-foreground`}
          >
            {t("library.groups.viewAllCourses")}
          </button>
          {courses.length === 0 ? (
            <p className="text-muted-foreground px-2 py-1.5 text-sm">
              {t("library.groups.noCourses")}
            </p>
          ) : null}
        </div>
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// 列表行（列表视图）

function ItemRow({
  item,
  selected,
  onSelect,
}: {
  item: LibraryItemOut;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const toggleFavorite = useToggleFavorite();
  const meta = [
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
        <Button
          variant="ghost"
          size="icon-sm"
          className={
            item.favorite ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          }
          aria-label={t("library.favoriteToggle")}
          aria-pressed={item.favorite}
          disabled={toggleFavorite.isPending}
          onClick={() =>
            toggleFavorite.mutate({ itemId: item.id, favorite: !item.favorite })
          }
        >
          <Star
            className={
              item.favorite ? "text-ink fill-current" : "text-muted-foreground"
            }
          />
        </Button>
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
// 网格卡片

type CardEntry = {
  id: string;
  sourceType: string;
  title: string;
  updatedAt: string;
  favorite: boolean;
};

function ItemCard({
  entry,
  selected,
  onSelect,
}: {
  entry: CardEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`hover:bg-surface-subtle flex h-full flex-col gap-2 rounded-xl border border-solid p-3 text-left transition-colors ${selected ? "bg-surface-strong" : ""}`}
    >
      <span className="flex items-center gap-2">
        <SourceTypeIcon sourceType={entry.sourceType} />
        <span className="text-label text-muted-foreground">
          {t(`library.sourceTypes.${entry.sourceType}`)}
        </span>
        {entry.favorite ? (
          <Star
            className="text-ink ml-auto size-3.5 fill-current"
            aria-label={t("library.favoriteToggle")}
          />
        ) : null}
      </span>
      <span className="text-body line-clamp-2 font-medium">{entry.title}</span>
      <span className="text-muted-foreground text-label mt-auto truncate">
        {formatDateTime(entry.updatedAt)}
      </span>
    </button>
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

function ItemInspector({ itemId }: { itemId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const detail = useLibraryItemDetail(itemId);
  const content = useLibraryItemContent(itemId);
  const item = detail.data;
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
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <SourceTypeIcon sourceType={item.source_type} />
        <div className="min-w-0 flex-1">
          <p className="text-body font-medium break-words">{item.title}</p>
          <p className="text-muted-foreground text-label">
            {t(`library.sourceTypes.${item.source_type}`)} ·{" "}
            {item.course_name ?? t("library.filters.unclassified")}
          </p>
        </div>
        <StatusTag tone={availabilityTone[item.availability] ?? "neutral"}>
          {t(`library.availability.${item.availability}`)}
        </StatusTag>
      </div>

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
}: {
  search: LibrarySearch;
  items: LibraryItemOut[];
  records: LibraryRecordOut[];
  assets: LibraryAssetOut[];
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
    return <ItemInspector itemId={search.sel} />;
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
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const domain = search.domain ?? "all";
  const view = search.view ?? "all";
  const layout = search.layout ?? "list";

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
  const itemsQuery = useLibraryItems(
    domain === "all" || domain === "sources" ? itemsParams : { limit: 1 },
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
    if (window.innerWidth < 1280) setInspectorOpen(true);
  };

  const backfill = itemsQuery.data?.backfill;
  const backfillActive =
    backfill !== null &&
    backfill !== undefined &&
    (backfill.status === "PENDING" || backfill.status === "RUNNING");
  const backfillFailed =
    backfill !== null && backfill !== undefined && backfill.status === "FAILED";

  const isListPending =
    (domain === "sources" || domain === "all") && itemsQuery.isPending;
  const isEmptyList =
    domain === "sources"
      ? allItems.length === 0
      : domain === "records"
        ? filteredRecords.length === 0
        : domain === "assets"
          ? filteredAssets.length === 0
          : allItems.length + filteredRecords.length + filteredAssets.length ===
            0;

  const inspectorBody = (
    <Inspector
      search={search}
      items={allItems}
      records={allRecords}
      assets={allAssets}
    />
  );

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-h-full py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-section font-section text-ink">
            {t("library.title")}
          </h1>
          <p className="text-muted-foreground text-body">
            {t("library.description")}
          </p>
        </div>
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
      </header>

      <div className="mt-4 grid min-h-0 gap-3 xl:grid-cols-[12rem_minmax(0,1fr)_clamp(20rem,28vw,28rem)]">
        <div className="hidden xl:block">
          <SidebarNav search={search} onSearchChange={onSearchChange} />
        </div>

        <main className="min-w-0 space-y-3">
          {/* 窄屏：智能视图以 chips 呈现（左导航在 xl 以下隐藏） */}
          <div className="flex flex-wrap gap-1.5 xl:hidden">
            {viewValues.map((chipView) => (
              <ToggleChip
                key={chipView}
                active={view === chipView}
                onClick={() =>
                  onSearchChange({
                    ...search,
                    view: chipView === "all" ? undefined : chipView,
                  })
                }
              >
                {t(`library.views.${chipView}`)}
              </ToggleChip>
            ))}
          </div>

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
            <TabsList className="w-full justify-start overflow-x-auto">
              {domainValues.map((tabDomain) => (
                <TabsTrigger key={tabDomain} value={tabDomain}>
                  {t(`library.domains.${tabDomain}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={search.q ?? ""}
              onChange={(event) =>
                onSearchChange({ ...search, q: event.target.value })
              }
              placeholder={t("library.filters.searchPlaceholder")}
              className="h-8 max-w-64"
              aria-label={t("library.filters.searchLabel")}
            />
            {domain !== "records" && domain !== "assets" ? (
              <div className="flex flex-wrap gap-1.5">
                {sourceTypeFilters.map((type) => (
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
                    {t(`library.sourceTypes.${type}`)}
                  </ToggleChip>
                ))}
              </div>
            ) : null}
            {domain !== "records" && domain !== "assets" ? (
              <div className="flex flex-wrap gap-1.5">
                {availabilityFilters.map((state) => (
                  <ToggleChip
                    key={state}
                    active={search.availability === state}
                    onClick={() =>
                      onSearchChange({
                        ...search,
                        availability:
                          search.availability === state ? undefined : state,
                      })
                    }
                  >
                    {t(`library.availability.${state}`)}
                  </ToggleChip>
                ))}
              </div>
            ) : null}
            {search.courseId ? (
              <ToggleChip
                active
                onClick={() =>
                  onSearchChange({ ...search, courseId: undefined })
                }
              >
                {t("library.filters.courseFilterActive")}
              </ToggleChip>
            ) : null}
            <div className="ml-auto flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("library.layout.list")}
                aria-pressed={layout === "list"}
                onClick={() => onSearchChange({ ...search, layout: undefined })}
              >
                <ListIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("library.layout.grid")}
                aria-pressed={layout === "grid"}
                onClick={() => onSearchChange({ ...search, layout: "grid" })}
              >
                <LayoutGrid />
              </Button>
            </div>
          </div>

          <div className="max-h-[calc(100vh-17rem)] overflow-y-auto pr-0.5">
            {isListPending ? (
              <div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
                <Spinner className="size-4" /> {t("library.loading")}
              </div>
            ) : isEmptyList ? (
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
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                {domain === "sources" || domain === "all"
                  ? allItems.map((item) => (
                      <li key={item.id}>
                        <ItemCard
                          entry={{
                            id: item.id,
                            sourceType: item.source_type,
                            title: item.title,
                            updatedAt: item.updated_at,
                            favorite: item.favorite,
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
                        <ItemCard
                          entry={{
                            id: record.id,
                            sourceType: captureSourceType(record.capture_type),
                            title: record.title,
                            updatedAt: record.updated_at,
                            favorite: false,
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
        </main>

        <aside className="bg-surface-raised hidden max-h-[calc(100vh-11rem)] overflow-y-auto rounded-xl border border-solid p-4 xl:block">
          {inspectorBody}
        </aside>
      </div>

      <Dialog open={inspectorOpen} onOpenChange={setInspectorOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto xl:hidden">
          <DialogHeader>
            <DialogTitle>{t("library.inspector.title")}</DialogTitle>
            <DialogDescription className="sr-only">
              {t("library.inspector.noneSelected")}
            </DialogDescription>
          </DialogHeader>
          {inspectorOpen ? inspectorBody : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}
