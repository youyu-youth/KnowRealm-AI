import { Search, SlidersHorizontal, X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  courseStatusLabelKeys,
  courseStatuses,
  courseTypeLabelKeys,
  courseTypes,
  educationStageLabelKeys,
  educationStages,
  isCourseType,
  isEducationStage,
  isLearningContext,
  learningContextLabelKeys,
  learningContexts,
} from "@/features/courses/courseOptions";
import {
  hasSpacesFilters,
  isSpacesSort,
  spacesSorts,
  type SpacesSearch,
} from "@/features/courses/spacesSearch";

const ALL_OPTION = "ALL";

const filterPillClassName =
  "text-body-dense min-h-7 h-auto rounded-md px-2.5 py-1 data-active:bg-spaces-soft data-active:text-spaces-accent";

type CourseFiltersProps = {
  search: SpacesSearch;
  onChange: (next: SpacesSearch) => void;
  actions?: ReactNode;
  heading?: ReactNode;
  description?: ReactNode;
  courses?: { status: "ACTIVE" | "ARCHIVED" }[];
};

export function CourseFilters({
  search,
  onChange,
  actions,
  heading,
  description,
  courses = [],
}: CourseFiltersProps) {
  const { t } = useTranslation();
  const contextFilter = search.learning_context ?? ALL_OPTION;
  const statusFilter = search.status ?? "ACTIVE";
  const sort = search.sort ?? "updated";
  const extraFilterCount = [search.education_stage, search.course_type].filter(
    (value) => value !== undefined,
  ).length;
  const hasFilters = hasSpacesFilters(search);
  const sortItems = spacesSorts.map((value) => ({
    value,
    label: t(`spaces.filters.sort.${value}`),
  }));

  function patch(next: Partial<SpacesSearch>) {
    onChange({ ...search, ...next });
  }

  function clearAll() {
    onChange({ sort: search.sort, view: search.view });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="mr-auto">{heading}</div>
      <div
        role="group"
        aria-label={t("spaces.filters.statusLabel")}
        className="border-border bg-background flex h-9 items-center gap-0.5 rounded-lg border p-1"
      >
        {courseStatuses.map((value) => (
          <Button
            key={value}
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={statusFilter === value}
            className={`text-body-dense h-auto min-h-7 rounded-md px-2.5 py-1 ${statusFilter === value ? "bg-spaces-soft text-spaces-accent" : "text-muted-foreground"}`}
            onClick={() =>
              patch({ status: value === "ACTIVE" ? undefined : value })
            }
          >
            {t(courseStatusLabelKeys[value])}
            <span className="text-label tabular-nums">
              {courses.filter((course) => course.status === value).length}
            </span>
          </Button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          items={sortItems}
          value={sort}
          onValueChange={(value) =>
            patch({ sort: isSpacesSort(value) ? value : undefined })
          }
        >
          <SelectTrigger
            className="bg-background h-9 w-36 rounded-lg"
            aria-label={t("spaces.filters.sortLabel")}
          >
            <SelectValue>{t(`spaces.filters.sort.${sort}`)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {spacesSorts.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`spaces.filters.sort.${value}`)}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>

        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="outline"
                className="bg-background h-9 rounded-lg"
              />
            }
          >
            <SlidersHorizontal data-icon="inline-start" aria-hidden="true" />
            {t("spaces.filters.more")}
            {extraFilterCount > 0 ? (
              <span className="bg-ink-strong text-paper text-label ml-0.5 inline-flex min-w-4 items-center justify-center rounded-full tabular-nums">
                {extraFilterCount}
              </span>
            ) : null}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                {t("spaces.filters.educationStage")}
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-40">
                <DropdownMenuRadioGroup
                  value={search.education_stage ?? ALL_OPTION}
                  onValueChange={(value) =>
                    patch({
                      education_stage: isEducationStage(value)
                        ? value
                        : undefined,
                    })
                  }
                >
                  <DropdownMenuRadioItem value={ALL_OPTION}>
                    {t("spaces.filters.allEducationStages")}
                  </DropdownMenuRadioItem>
                  {educationStages.map((value) => (
                    <DropdownMenuRadioItem key={value} value={value}>
                      {t(educationStageLabelKeys[value])}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                {t("spaces.filters.courseType")}
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-40">
                <DropdownMenuRadioGroup
                  value={search.course_type ?? ALL_OPTION}
                  onValueChange={(value) =>
                    patch({
                      course_type: isCourseType(value) ? value : undefined,
                    })
                  }
                >
                  <DropdownMenuRadioItem value={ALL_OPTION}>
                    {t("spaces.filters.allCourseTypes")}
                  </DropdownMenuRadioItem>
                  {courseTypes.map((value) => (
                    <DropdownMenuRadioItem key={value} value={value}>
                      {t(courseTypeLabelKeys[value])}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          </DropdownMenuContent>
        </DropdownMenu>

        {hasFilters ? (
          <Button
            type="button"
            variant="ghost"
            className="h-9 rounded-lg"
            disabled={!hasFilters}
            onClick={clearAll}
          >
            <X data-icon="inline-start" aria-hidden="true" />
            {t("spaces.filters.clear")}
          </Button>
        ) : null}
      </div>
      <div className="ml-auto">{actions}</div>
      <div className="text-body text-ink-muted w-full">{description}</div>
      <div className="flex w-full min-w-0 flex-wrap items-center gap-2 pt-1">
        {" "}
        <div className="relative min-w-52 flex-1 lg:max-w-72">
          <Search
            aria-hidden="true"
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          />
          <Input
            type="search"
            value={search.q ?? ""}
            onChange={(event) => patch({ q: event.target.value || undefined })}
            maxLength={100}
            className="bg-background h-9 rounded-lg pl-8"
            aria-label={t("spaces.filters.searchLabel")}
            placeholder={t("spaces.filters.searchPlaceholder")}
          />
        </div>
        <Tabs
          value={contextFilter}
          onValueChange={(value) =>
            patch({
              learning_context: isLearningContext(value) ? value : undefined,
            })
          }
        >
          <TabsList
            aria-label={t("spaces.filters.contextLabel")}
            className="border-border bg-background h-9 rounded-lg border p-1 shadow-none"
          >
            <TabsTrigger value={ALL_OPTION} className={filterPillClassName}>
              {t("spaces.filters.allContexts")}
            </TabsTrigger>
            {learningContexts.map((value) => (
              <TabsTrigger
                key={value}
                value={value}
                className={filterPillClassName}
              >
                {t(learningContextLabelKeys[value])}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
    </div>
  );
}
