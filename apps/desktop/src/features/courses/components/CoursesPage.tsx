import { useQuery } from "@tanstack/react-query";
import { BookOpenText, LayoutGrid, List, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type { Course } from "@/features/courses/api/types";
import { CourseCard } from "@/features/courses/components/CourseCard";
import { CourseFilters } from "@/features/courses/components/CourseFilters";
import { CourseList } from "@/features/courses/components/CourseList";
import { CreateCourseSheet } from "@/features/courses/components/CreateCourseSheet";
import { DeleteCourseDialog } from "@/features/courses/components/DeleteCourseDialog";
import { SpacesInsightsRail } from "@/features/courses/components/SpacesInsightsRail";
import {
  hasSpacesFilters,
  visibleSpacesCourses,
  type SpacesSearch,
} from "@/features/courses/spacesSearch";

type CoursesPageProps = {
  search: SpacesSearch;
  onSearchChange: (next: SpacesSearch) => void;
  onOpenCourse: (courseId: string) => void;
  onEditCourse: (courseId: string) => void;
};

export function CoursesPage({
  search,
  onSearchChange,
  onOpenCourse,
  onEditCourse,
}: CoursesPageProps) {
  const { t } = useTranslation();
  const [createOpen, setCreateOpen] = useState(false);
  const [deletingCourse, setDeletingCourse] = useState<Course | null>(null);
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
  });
  const allCourses = courses.data ?? [];
  const visibleCourses = visibleSpacesCourses(allCourses, search);
  const hasFilters = hasSpacesFilters(search);
  const view = search.view ?? "grid";
  const showFilters = hasFilters || allCourses.length > 0;

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-h-full min-w-0 py-8">
      <header className="flex items-start justify-between gap-8">
        <div className="max-w-reading">
          <h1 className="text-headline font-headline text-ink-strong">
            {t("spaces.title")}
          </h1>
          <p className="text-body text-muted-foreground mt-2">
            {t("spaces.description")}
          </p>
        </div>
        <Button className="shrink-0" onClick={() => setCreateOpen(true)}>
          <Plus data-icon="inline-start" aria-hidden="true" />
          {t("spaces.create")}
        </Button>
      </header>

      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(17rem,22vw,19.5rem)]">
        <div className="min-w-0">
          {showFilters ? (
            <CourseFilters search={search} onChange={onSearchChange} />
          ) : null}

          <div className="mt-4 flex min-h-8 items-center justify-between gap-3">
            <h2 className="text-section font-section text-ink-strong">
              {t("spaces.grid.allTitle", { count: visibleCourses.length })}
            </h2>
            <div
              role="group"
              aria-label={t("spaces.grid.viewLabel")}
              className="border-border bg-background flex h-8 items-center gap-0.5 rounded-lg border p-0.5"
            >
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-pressed={view === "grid"}
                aria-label={t("spaces.grid.viewGrid")}
                className={view === "grid" ? "bg-muted" : ""}
                onClick={() => onSearchChange({ ...search, view: undefined })}
              >
                <LayoutGrid aria-hidden="true" />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-pressed={view === "list"}
                aria-label={t("spaces.grid.viewList")}
                className={view === "list" ? "bg-muted" : ""}
                onClick={() => onSearchChange({ ...search, view: "list" })}
              >
                <List aria-hidden="true" />
              </Button>
            </div>
          </div>

          {courses.isPending ? (
            <p
              role="status"
              className="text-body text-muted-foreground mt-8 flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {t("spaces.loading")}
            </p>
          ) : courses.isError ? (
            <div className="border-border mt-8 border-t pt-8">
              <h2 className="text-section font-section text-ink">
                {t("spaces.errorTitle")}
              </h2>
              <p className="text-body text-muted-foreground mt-2">
                {t("spaces.errorDescription")}
              </p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => void courses.refetch()}
              >
                {t("spaces.retry")}
              </Button>
            </div>
          ) : visibleCourses.length === 0 &&
            hasFilters &&
            allCourses.length > 0 ? (
            <Empty className="border-border mt-8 flex-1 items-start justify-start gap-4 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
              <EmptyHeader className="max-w-reading items-start text-left">
                <EmptyTitle className="text-section font-section text-ink">
                  {t("spaces.noResultsTitle")}
                </EmptyTitle>
                <EmptyDescription className="max-w-reading text-body text-left">
                  {t("spaces.noResultsDescription")}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent className="items-start">
                <Button
                  variant="outline"
                  onClick={() =>
                    onSearchChange({ sort: search.sort, view: search.view })
                  }
                >
                  {t("spaces.filters.clear")}
                </Button>
              </EmptyContent>
            </Empty>
          ) : visibleCourses.length === 0 ? (
            <Empty className="border-border mt-8 flex-1 items-start justify-start gap-6 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
              <EmptyHeader className="max-w-reading items-start text-left">
                <EmptyMedia className="text-muted-foreground">
                  <BookOpenText className="size-5" aria-hidden="true" />
                </EmptyMedia>
                <EmptyTitle className="text-section font-section text-ink">
                  {t("spaces.emptyTitle")}
                </EmptyTitle>
                <EmptyDescription className="max-w-reading text-body text-left">
                  {t("spaces.emptyDescription")}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent className="items-start">
                <Button onClick={() => setCreateOpen(true)}>
                  {t("spaces.createFirst")}
                </Button>
              </EmptyContent>
            </Empty>
          ) : view === "list" ? (
            <CourseList
              courses={visibleCourses}
              onOpenCourse={onOpenCourse}
              onEditCourse={onEditCourse}
              onDeleteCourse={setDeletingCourse}
            />
          ) : (
            <div className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2">
              {visibleCourses.map((course) => (
                <CourseCard
                  key={course.id}
                  course={course}
                  onOpen={() => onOpenCourse(course.id)}
                  onEdit={() => onEditCourse(course.id)}
                  onDelete={() => setDeletingCourse(course)}
                />
              ))}
            </div>
          )}
        </div>

        <aside className="min-w-0" aria-label={t("spaces.insights.label")}>
          <SpacesInsightsRail courses={allCourses} />
        </aside>
      </div>

      <CreateCourseSheet open={createOpen} onOpenChange={setCreateOpen} />
      {deletingCourse ? (
        <DeleteCourseDialog
          course={deletingCourse}
          open
          onOpenChange={(next) => {
            if (!next) setDeletingCourse(null);
          }}
          onDeleted={() => setDeletingCourse(null)}
        />
      ) : null}
    </section>
  );
}
