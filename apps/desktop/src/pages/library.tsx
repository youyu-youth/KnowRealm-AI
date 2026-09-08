import { createFileRoute } from "@tanstack/react-router";
import { LibraryPage, type LibraryTab } from "@/features/library/LibraryPage";

// 页签是 URL 可表达的状态（desktop-react 规则）：缺省=全部、参数省略；
// 变化用 replace 落 URL，刷新/恢复不丢，但页签不算新历史记录。
type LibrarySearch = { tab?: Exclude<LibraryTab, "all"> };

export const Route = createFileRoute("/library")({
  validateSearch: (search: Record<string, unknown>): LibrarySearch => ({
    ...(search.tab === "records" ||
    search.tab === "knowledgePoints" ||
    search.tab === "courses"
      ? { tab: search.tab }
      : {}),
  }),
  component: LibraryRoute,
});

export function LibraryRoute() {
  const { tab = "all" } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <LibraryPage
      tab={tab}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/library",
          search: { tab: nextTab === "all" ? undefined : nextTab },
          replace: true,
        })
      }
    />
  );
}
