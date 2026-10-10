import { Search } from "lucide-react";
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
    <header>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-5 gap-y-2">
          <h1 className="text-inbox-title text-ink-strong font-headline">
            {t("inbox.title")}
          </h1>
          <p className="text-body-dense text-muted-foreground tabular-nums">
            {t("inbox.workspace.summary", {
              count: records.length,
              today: records.filter((record) => isToday(record.created_at))
                .length,
              upgradable: statuses.upgradable,
              processing: statuses.processing,
              failed: statuses.failed,
            })}
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <Tabs
            value={search.view ?? "desk"}
            onValueChange={(value) =>
              onChange({ view: value === "list" ? "list" : undefined })
            }
          >
            <TabsList
              aria-label={t("inbox.workspace.viewLabel")}
              className="border-border bg-paper h-auto rounded-lg border p-1 group-data-horizontal/tabs:h-auto"
            >
              {(["desk", "list"] as const).map((view) => (
                <TabsTrigger
                  key={view}
                  value={view}
                  className="data-active:bg-filter-active-background data-active:text-filter-active-foreground data-active:hover:text-filter-active-foreground dark:data-active:hover:text-filter-active-foreground text-body-dense dark:data-active:bg-filter-active-background dark:data-active:text-filter-active-foreground h-auto rounded-md px-4 py-1.5 data-active:border-transparent data-active:shadow-none dark:data-active:border-transparent"
                >
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
              className="text-body-dense h-auto min-h-9"
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
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Tabs
          className="max-w-full min-w-0 overflow-x-auto overflow-y-hidden pb-1"
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
            className="border-border bg-paper h-auto rounded-lg border p-1 shadow-none group-data-horizontal/tabs:h-auto"
          >
            {Object.entries(types).map(([value, count]) => (
              <TabsTrigger
                key={value}
                value={value}
                aria-label={t(`inbox.filters.type.${value}`)}
                className="data-active:bg-filter-active-background data-active:text-filter-active-foreground data-active:hover:text-filter-active-foreground dark:data-active:hover:text-filter-active-foreground text-body-dense dark:data-active:bg-filter-active-background dark:data-active:text-filter-active-foreground h-auto rounded-md px-3 py-1.5 data-active:border-transparent data-active:shadow-none dark:data-active:border-transparent"
              >
                {t(`inbox.filters.type.${value}`)}
                <span className="ml-1 tabular-nums" aria-hidden="true">
                  {count}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div
          className="border-border bg-paper mb-1 flex max-w-full flex-wrap items-center gap-1 rounded-lg border p-1"
          role="group"
          aria-label={t("inbox.filters.statusLabel")}
        >
          {Object.entries(statuses).map(([value, count]) => (
            <Button
              key={value}
              variant="ghost"
              size="sm"
              className={`text-body-dense h-auto px-3 py-1.5 ${(search.status ?? "unfiled") === value ? "bg-surface-subtle text-ink-strong" : "text-muted-foreground"}`}
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
        <div className="relative mb-1 ml-auto min-w-0 flex-1 basis-52 lg:max-w-72">
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
            className="bg-paper text-body-dense h-auto min-h-10 py-2 pl-9"
            aria-label={t("inbox.filters.searchLabel")}
            placeholder={t("inbox.filters.searchPlaceholder")}
          />
        </div>
      </div>
    </header>
  );
}
