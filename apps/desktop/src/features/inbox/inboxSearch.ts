const inboxTypeFilters = [
  "all",
  "quick-note",
  "paste",
  "audio",
  "document",
  "other",
] as const;

export type InboxTypeFilter = (typeof inboxTypeFilters)[number];

const inboxStatusFilters = [
  "unfiled",
  "upgradable",
  "processing",
  "failed",
] as const;

export type InboxStatusFilter = (typeof inboxStatusFilters)[number];

export type InboxSearch = {
  q?: string;
  type?: InboxTypeFilter;
  status?: InboxStatusFilter;
  page?: number;
  record?: string;
  view?: "desk" | "list";
  sort?: "newest" | "oldest" | "title";
};

export function isInboxTypeFilter(value: unknown): value is InboxTypeFilter {
  return (
    typeof value === "string" && inboxTypeFilters.some((item) => item === value)
  );
}

export function isInboxStatusFilter(
  value: unknown,
): value is InboxStatusFilter {
  return (
    typeof value === "string" &&
    inboxStatusFilters.some((item) => item === value)
  );
}
