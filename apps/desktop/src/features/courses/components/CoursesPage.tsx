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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type {
  CourseListQuery,
  CourseType,
  EducationStage,
} from "@/features/courses/api/types";
import { CourseList } from "@/features/courses/components/CourseList";
import { CreateCourseDialog } from "@/features/courses/components/CreateCourseDialog";
import {
  courseTypeLabelKeys,
  courseTypes,
  educationStageLabelKeys,
  educationStages,
} from "@/features/courses/courseOptions";

const ALL_FILTERS = "ALL";

function isEducationStage(value: string | null): value is EducationStage {
  return value !== null && educationStages.some((stage) => stage === value);
}

function isCourseType(value: string | null): value is CourseType {
  return value !== null && courseTypes.some((type) => type === value);
}

type CoursesPageProps = {
  filters: CourseListQuery;
  onFiltersChange: (filters: CourseListQuery) => void;
};

export function CoursesPage({ filters, onFiltersChange }: CoursesPageProps) {
  const { t } = useTranslation();
  const [createOpen, setCreateOpen] = useState(false);
  const courses = useQuery({
    queryKey: courseKeys.list(filters),
    queryFn: () => courseApi.list(filters),
  });
  const hasFilters = Boolean(
    filters.q || filters.education_stage || filters.course_type,
  );
  const showFilters = hasFilters || Boolean(courses.data?.length);
  const educationStageItems = [
    { value: ALL_FILTERS, label: t("spaces.filters.allEducationStages") },
    ...educationStages.map((value) => ({
      value,
      label: t(educationStageLabelKeys[value]),
    })),
  ];
  const courseTypeItems = [
    { value: ALL_FILTERS, label: t("spaces.filters.allCourseTypes") },
    ...courseTypes.map((value) => ({
      value,
      label: t(courseTypeLabelKeys[value]),
    })),
  ];

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("q");
    const q = typeof value === "string" ? value.trim() : "";
    onFiltersChange({ ...filters, q: q || undefined });
  }

  function handleEducationStage(value: string | null) {
    onFiltersChange({
      ...filters,
      education_stage: isEducationStage(value) ? value : undefined,
    });
  }

  function handleCourseType(value: string | null) {
    onFiltersChange({
      ...filters,
      course_type: isCourseType(value) ? value : undefined,
    });
  }

  function clearFilters(event: React.MouseEvent<HTMLButtonElement>) {
    event.currentTarget.form?.reset();
    onFiltersChange({});
  }

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
        <form
          className="border-border mt-8 border-t pt-5"
          onSubmit={handleSearch}
        >
          <FieldGroup className="grid gap-3 md:grid-cols-[minmax(15rem,1fr)_11rem_11rem_auto] md:items-end">
            <Field>
              <FieldLabel htmlFor="course-search">
                {t("spaces.filters.searchLabel")}
              </FieldLabel>
              <div className="flex gap-2">
                <Input
                  id="course-search"
                  key={filters.q ?? "empty"}
                  name="q"
                  type="search"
                  defaultValue={filters.q ?? ""}
                  maxLength={100}
                  placeholder={t("spaces.filters.searchPlaceholder")}
                />
                <Button type="submit" variant="outline">
                  {t("spaces.filters.searchAction")}
                </Button>
              </div>
            </Field>
            <Field>
              <FieldLabel htmlFor="education-stage-filter">
                {t("spaces.filters.educationStage")}
              </FieldLabel>
              <Select
                items={educationStageItems}
                value={filters.education_stage ?? ALL_FILTERS}
                onValueChange={handleEducationStage}
              >
                <SelectTrigger id="education-stage-filter" className="w-full">
                  <SelectValue>
                    {filters.education_stage
                      ? t(educationStageLabelKeys[filters.education_stage])
                      : t("spaces.filters.allEducationStages")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={ALL_FILTERS}>
                      {t("spaces.filters.allEducationStages")}
                    </SelectItem>
                    {educationStages.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(educationStageLabelKeys[value])}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="course-type-filter">
                {t("spaces.filters.courseType")}
              </FieldLabel>
              <Select
                items={courseTypeItems}
                value={filters.course_type ?? ALL_FILTERS}
                onValueChange={handleCourseType}
              >
                <SelectTrigger id="course-type-filter" className="w-full">
                  <SelectValue>
                    {filters.course_type
                      ? t(courseTypeLabelKeys[filters.course_type])
                      : t("spaces.filters.allCourseTypes")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={ALL_FILTERS}>
                      {t("spaces.filters.allCourseTypes")}
                    </SelectItem>
                    {courseTypes.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(courseTypeLabelKeys[value])}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Button
              type="button"
              variant="ghost"
              disabled={!hasFilters}
              onClick={clearFilters}
            >
              {t("spaces.filters.clear")}
            </Button>
          </FieldGroup>
        </form>
      ) : null}

      {courses.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-10 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.loading")}
        </p>
      ) : courses.isError ? (
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
            onClick={() => void courses.refetch()}
          >
            {t("spaces.retry")}
          </Button>
        </div>
      ) : courses.data.length === 0 && hasFilters ? (
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
      ) : courses.data.length === 0 ? (
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
        <CourseList courses={courses.data} />
      )}

      <CreateCourseDialog open={createOpen} onOpenChange={setCreateOpen} />
    </section>
  );
}
