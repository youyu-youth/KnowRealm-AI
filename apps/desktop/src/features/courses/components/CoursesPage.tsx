import { useQuery } from "@tanstack/react-query";
import { BookOpenText, Plus } from "lucide-react";
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
import type { Course, LearningContext } from "@/features/courses/api/types";
import { CourseCard } from "@/features/courses/components/CourseCard";
import { CourseFilters } from "@/features/courses/components/CourseFilters";
import { SpacesViewSwitcher } from "@/features/courses/components/SpacesViewSwitcher";
import { CourseTracks } from "@/features/courses/components/CourseTracks";
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
  const [createContext, setCreateContext] = useState<LearningContext>();
  const [deletingCourse, setDeletingCourse] = useState<Course | null>(null);
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
  });
  const allCourses = courses.data ?? [];
  const visibleCourses = visibleSpacesCourses(allCourses, search);
  const hasFilters = hasSpacesFilters(search);
  const view = search.view ?? "tracks";

  return (
    <section className="spaces-workspace px-content mx-auto flex min-h-full min-w-0 flex-col py-5">
      <header>
        <CourseFilters
          search={search}
          onChange={onSearchChange}
          courses={allCourses}
          heading={
            <div className="flex flex-wrap items-baseline gap-3">
              <h1 className="text-spaces-title font-headline text-ink-strong">
                {t("spaces.title")}
              </h1>
              <span className="text-body text-ink-muted">
                {t("spaces.grid.allTitle", { count: visibleCourses.length })}
              </span>
            </div>
          }
          description={t("spaces.description")}
          actions={
            <div className="flex flex-wrap items-center gap-3">
              <SpacesViewSwitcher search={search} onChange={onSearchChange} />
              <Button
                onClick={() => {
                  setCreateContext(undefined);
                  setCreateOpen(true);
                }}
              >
                <Plus data-icon="inline-start" aria-hidden="true" />
                {t("spaces.create")}
              </Button>
            </div>
          }
        />
      </header>
      <div className="mt-2 flex min-w-0 flex-1 flex-col gap-3">
        <div className="min-w-0">
          <p className="text-label text-ink-muted mt-2">
            {t("spaces.tracks.hint")}
          </p>
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
                <Button
                  onClick={() => {
                    setCreateContext(undefined);
                    setCreateOpen(true);
                  }}
                >
                  {t("spaces.createFirst")}
                </Button>
              </EmptyContent>
            </Empty>
          ) : (
            <div key={view} className="mt-3 min-w-0">
              {view === "tracks" ? (
                <CourseTracks
                  courses={visibleCourses}
                  context={search.learning_context}
                  onCreate={(context) => {
                    setCreateContext(context);
                    setCreateOpen(true);
                  }}
                  onOpenCourse={onOpenCourse}
                  onEditCourse={onEditCourse}
                  onDeleteCourse={setDeletingCourse}
                />
              ) : view === "list" ? (
                <CourseList
                  courses={visibleCourses}
                  onOpenCourse={onOpenCourse}
                  onEditCourse={onEditCourse}
                  onDeleteCourse={setDeletingCourse}
                />
              ) : (
                <div className="spaces-course-grid">
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
          )}
        </div>

        <aside
          className="spaces-insights-dock mt-auto min-w-0"
          aria-label={t("spaces.insights.label")}
        >
          <SpacesInsightsRail courses={allCourses} />
        </aside>
      </div>

      <CreateCourseSheet
        open={createOpen}
        onOpenChange={setCreateOpen}
        initialLearningContext={createContext}
      />
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
