import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
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
import type { CourseListQuery } from "@/features/courses/api/types";
import {
  courseTypeLabelKeys,
  courseTypes,
  educationStageLabelKeys,
  educationStages,
  isCourseType,
  isEducationStage,
} from "@/features/courses/courseOptions";

const ALL_FILTERS = "ALL";

type CourseFiltersProps = {
  filters: CourseListQuery;
  onChange: (filters: CourseListQuery) => void;
};

export function CourseFilters({ filters, onChange }: CourseFiltersProps) {
  const { t } = useTranslation();
  const hasFilters = Boolean(
    filters.q || filters.education_stage || filters.course_type,
  );
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
    onChange({ ...filters, q: q || undefined });
  }

  function clearFilters(event: React.MouseEvent<HTMLButtonElement>) {
    event.currentTarget.form?.reset();
    onChange({});
  }

  return (
    <form className="border-border mt-8 border-t pt-5" onSubmit={handleSearch}>
      <FieldGroup className="grid gap-3 md:grid-cols-[minmax(var(--spacing-filter-search),1fr)_var(--spacing-filter-select)_var(--spacing-filter-select)_auto] md:items-end">
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
            onValueChange={(value) =>
              onChange({
                ...filters,
                education_stage: isEducationStage(value) ? value : undefined,
              })
            }
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
            onValueChange={(value) =>
              onChange({
                ...filters,
                course_type: isCourseType(value) ? value : undefined,
              })
            }
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
  );
}
