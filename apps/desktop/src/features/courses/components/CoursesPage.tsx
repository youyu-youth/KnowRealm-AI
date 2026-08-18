import { useQuery } from "@tanstack/react-query";
import { BookOpenText } from "lucide-react";
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
import type { CourseListQuery } from "@/features/courses/api/types";
import { CourseFilters } from "@/features/courses/components/CourseFilters";
import { CourseList } from "@/features/courses/components/CourseList";
import { CreateCourseDialog } from "@/features/courses/components/CreateCourseDialog";

type CoursesPageProps = {
  filters: CourseListQuery;
  onFiltersChange: (filters: CourseListQuery) => void;
  onOpenCourse: (courseId: string) => void;
};

export function CoursesPage({
  filters,
  onFiltersChange,
  onOpenCourse,
}: CoursesPageProps) {
  const { t } = useTranslation();
  const [createOpen, setCreateOpen] = useState(false);
  const courses = useQuery({
    queryKey: courseKeys.list(filters),
    queryFn: () => courseApi.list(filters),
  });
  const hasFilters = Boolean(
    filters.q || filters.education_stage || filters.course_type,
  );
  const visibleCourses = courses.data ?? [];
  const shouldCheckTrueEmpty =
    hasFilters && visibleCourses.length === 0 && courses.isSuccess;
  const allCourses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: shouldCheckTrueEmpty,
  });
  const showFilters = hasFilters || Boolean(courses.data?.length);
  const checkingTrueEmpty =
    shouldCheckTrueEmpty &&
    allCourses.isPending &&
    allCourses.fetchStatus === "fetching";
  const hasQueryError =
    courses.isError || (shouldCheckTrueEmpty && allCourses.isError);

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
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
          {t("spaces.create")}
        </Button>
      </header>

      {showFilters ? (
        <CourseFilters filters={filters} onChange={onFiltersChange} />
      ) : null}

      {courses.isPending || checkingTrueEmpty ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-10 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.loading")}
        </p>
      ) : hasQueryError ? (
        <div className="border-border mt-10 border-t pt-8">
          <h2 className="text-section font-section text-ink">
            {t("spaces.errorTitle")}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {t("spaces.errorDescription")}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => {
              void courses.refetch();
              if (shouldCheckTrueEmpty && allCourses.isError)
                void allCourses.refetch();
            }}
          >
            {t("spaces.retry")}
          </Button>
        </div>
      ) : visibleCourses.length === 0 &&
        hasFilters &&
        allCourses.data?.length ? (
        <Empty className="mt-10 flex-1 items-start justify-start gap-4 rounded-none border-0 bg-transparent px-0 py-8 text-left">
          <EmptyHeader className="max-w-reading items-start text-left">
            <EmptyTitle className="text-section font-section text-ink">
              {t("spaces.noResultsTitle")}
            </EmptyTitle>
            <EmptyDescription className="max-w-reading text-body text-left">
              {t("spaces.noResultsDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : visibleCourses.length === 0 ? (
        <Empty className="mt-12 flex-1 items-start justify-start gap-6 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
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
      ) : (
        <CourseList courses={visibleCourses} onOpenCourse={onOpenCourse} />
      )}

      <CreateCourseDialog open={createOpen} onOpenChange={setCreateOpen} />
    </section>
  );
}
