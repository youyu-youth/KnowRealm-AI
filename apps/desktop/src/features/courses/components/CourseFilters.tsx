import { Search, SlidersHorizontal, X } from "lucide-react";
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
  "h-7 rounded-md px-2.5 text-[13px] transition-colors duration-[120ms] ease-out data-active:border-transparent data-active:bg-black data-active:text-white data-active:shadow-sm dark:data-active:bg-white dark:data-active:text-black";

type CourseFiltersProps = {
  search: SpacesSearch;
  onChange: (next: SpacesSearch) => void;
};

export function CourseFilters({ search, onChange }: CourseFiltersProps) {
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
            className={`h-7 rounded-md px-2.5 text-[13px] transition-colors duration-[120ms] ease-out ${statusFilter === value ? "bg-muted text-foreground" : "text-muted-foreground"}`}
            onClick={() =>
              patch({ status: value === "ACTIVE" ? undefined : value })
            }
          >
            {t(courseStatusLabelKeys[value])}
          </Button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
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
              <span className="bg-ink-strong text-paper ml-0.5 inline-flex size-4 items-center justify-center rounded-full text-[10px] tabular-nums">
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
      </div>
    </div>
  );
}
