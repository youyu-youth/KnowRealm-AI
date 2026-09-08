import { useNavigate } from "@tanstack/react-router";
import {
  FileText,
  GraduationCap,
  Library,
  Star,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
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
import { useSearchResults } from "@/features/search/api/queries";
import type {
  SearchCourseItem,
  SearchKnowledgePointItem,
  SearchRecordItem,
} from "@/features/search/api/search";
import { SearchResultItem } from "@/features/search/components/SearchResultItem";

// 资产库是完整检索视图，每类上限取后端校验最大值（命令面板用后端默认的每类 5 条）。
const LIBRARY_SEARCH_LIMIT = 50;

const tabLabelKeys = {
  all: "library.tabs.all",
  records: "library.tabs.records",
  knowledgePoints: "library.tabs.knowledgePoints",
  courses: "library.tabs.courses",
} as const;

export type LibraryTab = keyof typeof tabLabelKeys;

function isLibraryTab(value: unknown): value is LibraryTab {
  return typeof value === "string" && value in tabLabelKeys;
}

const rowClass =
  "hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 flex w-full rounded-md px-2 py-2 text-left transition-colors focus-visible:ring-3 focus-visible:outline-hidden";
const groupHeadingClass = "text-label text-muted-foreground font-label";

// 结果行：命中行的可点击容器，命中展示复用命令面板的 SearchResultItem。
function ResultRow({
  icon,
  title,
  snippet,
  context,
  onSelect,
}: {
  icon: LucideIcon;
  title: string;
  snippet: string;
  context: string | null;
  onSelect: () => void;
}) {
  return (
    <button type="button" onClick={onSelect} className={rowClass}>
      <SearchResultItem
        icon={icon}
        title={title}
        snippet={snippet}
        context={context}
        className="w-full"
      />
    </button>
  );
}

export function LibraryPage({
  tab,
  onTabChange,
}: {
  tab: LibraryTab;
  onTabChange: (tab: LibraryTab) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const trimmed = query.trim();
  const search = useSearchResults(trimmed, LIBRARY_SEARCH_LIMIT);
  const results = search.data;
  const hasQuery = trimmed.length > 0;

  // 类型过滤在展示层取对应分组：切页签只改 URL，不重发请求。
  const showRecords = tab === "all" || tab === "records";
  const showKnowledgePoints = tab === "all" || tab === "knowledgePoints";
  const showCourses = tab === "all" || tab === "courses";
  const total = results
    ? results.records.length +
      results.knowledge_points.length +
      results.courses.length
    : 0;
  const visibleCount = results
    ? (showRecords ? results.records.length : 0) +
      (showKnowledgePoints ? results.knowledge_points.length : 0) +
      (showCourses ? results.courses.length : 0)
    : 0;

  const selectCourse = (item: SearchCourseItem) => {
    void navigate({
      to: "/spaces/$courseId",
      params: { courseId: item.id },
      search: { tab: "overview" },
    });
  };
  const selectRecord = (item: SearchRecordItem) => {
    void navigate({
      to: "/records/$recordId",
      params: { recordId: item.id },
    });
  };
  const selectKnowledgePoint = (item: SearchKnowledgePointItem) => {
    void navigate({
      to: "/records/$recordId",
      params: { recordId: item.record_id },
      search: { tab: "knowledge-points" },
    });
  };

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
      <header>
        <h1 className="text-headline font-headline text-ink-strong">
          {t("library.title")}
        </h1>
        <p className="text-body text-muted-foreground mt-2">
          {t("library.description")}
        </p>
      </header>

      <Input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        maxLength={100}
        placeholder={t("library.placeholder")}
        aria-label={t("library.searchLabel")}
        className="mt-8"
      />

      {hasQuery ? (
        <Tabs
          value={tab}
          onValueChange={(value) =>
            onTabChange(isLibraryTab(value) ? value : "all")
          }
          className="mt-4"
        >
          <TabsList>
            {(Object.keys(tabLabelKeys) as LibraryTab[]).map((value) => (
              <TabsTrigger key={value} value={value}>
                {t(tabLabelKeys[value])}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      ) : null}

      {!hasQuery ? (
        // 空查询走 #42 引导卡：说明资产库的用途，不做向导流程。
        <Empty className="mt-12 flex-1 items-start justify-start gap-6 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
          <EmptyHeader className="max-w-reading items-start text-left">
            <EmptyMedia className="text-muted-foreground">
              <Library className="size-5" aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle className="text-section font-section text-ink">
              {t("library.emptyTitle")}
            </EmptyTitle>
            <EmptyDescription className="max-w-reading text-body text-left">
              {t("library.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : search.isError && results === undefined ? (
        <div className="border-border mt-10 border-t pt-8">
          <h2 className="text-section font-section text-ink">
            {t("library.errorTitle")}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {t("library.errorDescription")}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => void search.refetch()}
          >
            {t("library.retry")}
          </Button>
        </div>
      ) : results === undefined ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-10 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("library.loading")}
        </p>
      ) : total === 0 ? (
        <Empty className="mt-12 flex-1 items-start justify-start gap-6 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
          <EmptyHeader className="max-w-reading items-start text-left">
            <EmptyTitle className="text-section font-section text-ink">
              {t("library.noResultsTitle")}
            </EmptyTitle>
            <EmptyDescription className="max-w-reading text-body text-left">
              {t("library.noResultsDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : visibleCount === 0 ? (
        <p className="text-body text-muted-foreground mt-6">
          {t("library.noResultsInFilter")}
        </p>
      ) : (
        <div className="mt-2">
          {showRecords && results.records.length > 0 ? (
            <div className="mt-4">
              <h2 className={groupHeadingClass}>
                {t("library.groups.records")}
              </h2>
              <div className="mt-1 flex flex-col">
                {results.records.map((item) => (
                  <ResultRow
                    key={item.id}
                    icon={FileText}
                    title={item.title}
                    snippet={item.snippet}
                    context={item.course_name}
                    onSelect={() => selectRecord(item)}
                  />
                ))}
              </div>
            </div>
          ) : null}
          {showKnowledgePoints && results.knowledge_points.length > 0 ? (
            <div className="mt-4">
              <h2 className={groupHeadingClass}>
                {t("library.groups.knowledgePoints")}
              </h2>
              <div className="mt-1 flex flex-col">
                {results.knowledge_points.map((item) => (
                  <ResultRow
                    key={item.id}
                    icon={Star}
                    title={item.title}
                    snippet={item.snippet}
                    context={item.course_name}
                    onSelect={() => selectKnowledgePoint(item)}
                  />
                ))}
              </div>
            </div>
          ) : null}
          {showCourses && results.courses.length > 0 ? (
            <div className="mt-4">
              <h2 className={groupHeadingClass}>
                {t("library.groups.courses")}
              </h2>
              <div className="mt-1 flex flex-col">
                {results.courses.map((item) => (
                  <ResultRow
                    key={item.id}
                    icon={GraduationCap}
                    title={item.title}
                    snippet={item.snippet}
                    context={null}
                    onSelect={() => selectCourse(item)}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
