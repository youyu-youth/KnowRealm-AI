import { LayoutGrid, List, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  isInboxTypeFilter,
  type InboxSearch,
} from "@/features/inbox/inboxSearch";
import {
  ORGANIZABLE_STATUSES,
  PROCESSING_STATUSES,
  isToday,
} from "@/features/inbox/inboxPresentation";
import type { InboxRecordOut } from "@/features/records/api/types";

export function InboxToolbar({
  records,
  search,
  onChange,
  onFilterChange,
}: {
  records: InboxRecordOut[];
  search: InboxSearch;
  onChange: (next: Partial<InboxSearch>) => void;
  onFilterChange: (next: Partial<InboxSearch>) => void;
}) {
  const { t } = useTranslation();
  const types = {
    all: records.length,
    "quick-note": records.filter(
      (record) => record.capture_type === "QUICK_NOTE",
    ).length,
    paste: records.filter((record) => record.capture_type === "PASTE").length,
    audio: records.filter((record) =>
      ["RECORDING", "AUDIO_IMPORT"].includes(record.capture_type),
    ).length,
    document: records.filter(
      (record) => record.capture_type === "DOCUMENT_IMPORT",
    ).length,
    other: records.filter((record) =>
      ["MULTI_SOURCE", "CLIP"].includes(record.capture_type),
    ).length,
  };
  const statuses = {
    unfiled: records.length,
    upgradable: records.filter((record) =>
      ORGANIZABLE_STATUSES.has(record.status),
    ).length,
    processing: records.filter((record) =>
      PROCESSING_STATUSES.has(record.status),
    ).length,
    failed: records.filter((record) => record.status === "FAILED").length,
  };
  return (
    <header className="inbox-toolbar">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-inbox-title text-ink font-headline">
            {t("inbox.title")}
          </h1>
          <p className="text-body-dense text-muted-foreground mt-1 tabular-nums">
            {t("inbox.workspace.summary", {
              count: records.length,
              today: records.filter((record) => isToday(record.created_at))
                .length,
            })}
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 basis-52 lg:w-64 lg:flex-none">
            <Search
              aria-hidden="true"
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            />
            <Input
              type="search"
              value={search.q ?? ""}
              onChange={(event) =>
                onFilterChange({ q: event.target.value || undefined })
              }
              maxLength={100}
              className="bg-surface-raised text-body-dense h-9 pl-9"
              aria-label={t("inbox.filters.searchLabel")}
              placeholder={t("inbox.filters.searchPlaceholder")}
            />
          </div>
          <Tabs
            value={search.view ?? "desk"}
            onValueChange={(value) =>
              onChange({ view: value === "list" ? "list" : undefined })
            }
          >
            <TabsList
              aria-label={t("inbox.workspace.viewLabel")}
              className="bg-surface-strong h-9 rounded-lg p-1 group-data-horizontal/tabs:h-9"
            >
              {(["desk", "list"] as const).map((view) => (
                <TabsTrigger
                  key={view}
                  value={view}
                  className="inbox-view-tab text-body-dense data-active:bg-surface-raised data-active:text-ink dark:data-active:bg-surface-raised dark:data-active:text-ink h-full gap-1.5 rounded-md px-3 data-active:border-transparent data-active:shadow-none dark:data-active:border-transparent"
                >
                  {view === "desk" ? (
                    <LayoutGrid aria-hidden="true" />
                  ) : (
                    <List aria-hidden="true" />
                  )}
                  {t(`inbox.workspace.${view}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Select
            value={search.sort ?? "newest"}
            onValueChange={(value) =>
              onChange({
                sort:
                  value === "oldest" || value === "title" ? value : undefined,
                page: undefined,
              })
            }
          >
            <SelectTrigger
              className="bg-surface-raised text-body-dense h-9"
              aria-label={t("inbox.workspace.sortLabel")}
            >
              <SelectValue>
                {t(`inbox.workspace.sort.${search.sort ?? "newest"}`)}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="inbox-menu" alignItemWithTrigger={false}>
              {(["newest", "oldest", "title"] as const).map((sort) => (
                <SelectItem key={sort} value={sort}>
                  {t(`inbox.workspace.sort.${sort}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <Tabs
          className="-ml-1 max-w-full min-w-0 overflow-x-auto overflow-y-hidden p-1"
          value={search.type ?? "all"}
          onValueChange={(value) =>
            onFilterChange({
              type:
                isInboxTypeFilter(value) && value !== "all" ? value : undefined,
            })
          }
        >
          <TabsList
            aria-label={t("inbox.filters.typeLabel")}
            className="h-auto gap-1 rounded-none bg-transparent p-0 shadow-none group-data-horizontal/tabs:h-auto"
          >
            {Object.entries(types).map(([value, count]) => (
              <TabsTrigger
                key={value}
                value={value}
                aria-label={t(`inbox.filters.type.${value}`)}
                className="inbox-type-tab data-active:bg-filter-active-background data-active:text-filter-active-foreground data-active:hover:text-filter-active-foreground dark:data-active:hover:text-filter-active-foreground text-body-dense dark:data-active:bg-filter-active-background dark:data-active:text-filter-active-foreground h-9 rounded-lg px-3 data-active:border-transparent data-active:shadow-none dark:data-active:border-transparent"
              >
                {t(`inbox.filters.type.${value}`)}
                <span
                  className="inbox-filter-count tabular-nums"
                  aria-hidden="true"
                >
                  {count}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div
          className="flex max-w-full flex-wrap items-center gap-1"
          role="group"
          aria-label={t("inbox.filters.statusLabel")}
        >
          {Object.entries(statuses).map(([value, count]) => (
            <Button
              key={value}
              variant="ghost"
              size="sm"
              className={`text-body-dense h-8 gap-1.5 px-2.5 ${(search.status ?? "unfiled") === value ? "bg-surface-strong text-ink" : "text-muted-foreground"}`}
              aria-pressed={(search.status ?? "unfiled") === value}
              aria-label={t(`inbox.filters.status.${value}`)}
              onClick={() =>
                onFilterChange({
                  status:
                    value === "upgradable" ||
                    value === "processing" ||
                    value === "failed"
                      ? value
                      : undefined,
                })
              }
            >
              {t(`inbox.filters.status.${value}`)}
              <span className="tabular-nums" aria-hidden="true">
                {count}
              </span>
            </Button>
          ))}
        </div>
        {search.q ||
        (search.type && search.type !== "all") ||
        (search.status && search.status !== "unfiled") ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() =>
              onFilterChange({
                q: undefined,
                type: undefined,
                status: undefined,
              })
            }
          >
            <X aria-hidden="true" />
            {t("inbox.filters.clear")}
          </Button>
        ) : null}
      </div>
    </header>
  );
}
