import { createFileRoute } from "@tanstack/react-router";
import { LibraryPage } from "@/features/library/LibraryPage";
import {
  isLibraryAvailabilityFilter,
  isLibraryDomain,
  isLibraryLayout,
  isLibrarySelType,
  isLibrarySourceTypeFilter,
  isLibraryView,
  type LibrarySearch,
} from "@/features/library/librarySearch";

// 筛选/视图/选中对象全部进 searchParams（desktop-react 规则）：缺省值参数省略、
// 变化 replace 落 URL，刷新/分享后视图可恢复。
export const Route = createFileRoute("/library")({
  validateSearch: (search: Record<string, unknown>): LibrarySearch => ({
    ...(isLibraryDomain(search.domain) && search.domain !== "all"
      ? { domain: search.domain }
      : {}),
    ...(isLibraryView(search.view) && search.view !== "all"
      ? { view: search.view }
      : {}),
    ...(isLibraryLayout(search.layout) ? { layout: search.layout } : {}),
    ...(isLibrarySourceTypeFilter(search.sourceType)
      ? { sourceType: search.sourceType }
      : {}),
    ...(isLibraryAvailabilityFilter(search.availability)
      ? { availability: search.availability }
      : {}),
    ...(typeof search.courseId === "string"
      ? { courseId: search.courseId }
      : {}),
    ...(typeof search.q === "string" ? { q: search.q } : {}),
    ...(typeof search.sel === "string" ? { sel: search.sel } : {}),
    ...(isLibrarySelType(search.selType) ? { selType: search.selType } : {}),
  }),
  component: LibraryRoute,
});

export function LibraryRoute() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <LibraryPage
      search={search}
      onSearchChange={(next) =>
        void navigate({ to: "/library", search: next, replace: true })
      }
    />
  );
}
