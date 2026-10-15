// 资料库 URL search 契约（desktop-react 规则：URL 能表达的筛选/视图全进 searchParams）。
const libraryDomains = ["all", "sources", "records", "assets"] as const;
const libraryViews = [
  "all",
  "recent",
  "favorites",
  "needsReview",
  "archived",
  "trash",
] as const;
const libraryLayouts = ["list", "grid"] as const;
const librarySourceTypes = [
  "AUDIO",
  "DOCUMENT",
  "WEB",
  "BOOK",
  "TEXT",
] as const;
const libraryAvailabilities = [
  "PROCESSING",
  "RETRIEVABLE",
  "FAILED",
  "EMPTY",
] as const;
const librarySelTypes = ["item", "record", "asset"] as const;

export type LibraryDomain = (typeof libraryDomains)[number];
export type LibraryView = (typeof libraryViews)[number];
export type LibraryLayout = (typeof libraryLayouts)[number];
export type LibrarySourceTypeFilter = (typeof librarySourceTypes)[number];
export type LibraryAvailabilityFilter = (typeof libraryAvailabilities)[number];
export type LibrarySelType = (typeof librarySelTypes)[number];

export type LibrarySearch = {
  domain?: Exclude<LibraryDomain, "all">;
  view?: Exclude<LibraryView, "all">;
  layout?: LibraryLayout;
  sourceType?: LibrarySourceTypeFilter;
  availability?: LibraryAvailabilityFilter;
  courseId?: string;
  q?: string;
  sel?: string;
  selType?: LibrarySelType;
};

export function isLibraryDomain(value: unknown): value is LibraryDomain {
  return (
    typeof value === "string" && libraryDomains.some((item) => item === value)
  );
}

export function isLibraryView(value: unknown): value is LibraryView {
  return (
    typeof value === "string" && libraryViews.some((item) => item === value)
  );
}

export function isLibraryLayout(value: unknown): value is LibraryLayout {
  return (
    typeof value === "string" && libraryLayouts.some((item) => item === value)
  );
}

export function isLibrarySourceTypeFilter(
  value: unknown,
): value is LibrarySourceTypeFilter {
  return (
    typeof value === "string" &&
    librarySourceTypes.some((item) => item === value)
  );
}

export function isLibraryAvailabilityFilter(
  value: unknown,
): value is LibraryAvailabilityFilter {
  return (
    typeof value === "string" &&
    libraryAvailabilities.some((item) => item === value)
  );
}

export function isLibrarySelType(value: unknown): value is LibrarySelType {
  return (
    typeof value === "string" && librarySelTypes.some((item) => item === value)
  );
}
