import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ToggleChip } from "@/components/common/ToggleChip";
import { Spinner } from "@/components/ui/spinner";
import type { BrainConceptListQuery } from "@/features/courses/api/types";
import type { BrainConcept } from "@/features/courses/api/types";
import { useCourseBrainConcepts } from "@/features/courses/api/courseBrain";
import { cn } from "@/lib/utils";

type ConceptStatusFilter = NonNullable<BrainConceptListQuery["status"]>;

const FILTERS: { value: ConceptStatusFilter; labelKey: string }[] = [
  {
    value: "CONFIRMED",
    labelKey: "spaces.courseDetail.brain.concepts.filterConfirmed",
  },
  {
    value: "CANDIDATE",
    labelKey: "spaces.courseDetail.brain.concepts.filterCandidate",
  },
];

type CourseBrainConceptListProps = {
  courseId: string;
  selectedId: string | null;
  onSelect: (concept: BrainConcept) => void;
  className?: string;
};

/** 概念列表视图：正式/候选两态筛选；行点击打开概念详情面板。 */
export function CourseBrainConceptList({
  courseId,
  selectedId,
  onSelect,
  className,
}: CourseBrainConceptListProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ConceptStatusFilter>("CONFIRMED");
  const concepts = useCourseBrainConcepts(courseId, { status });

  return (
    <div className={cn("flex min-w-0 flex-col gap-3", className)}>
      <div
        role="group"
        aria-label={t("spaces.courseDetail.brain.concepts.title")}
        className="flex items-center gap-1"
      >
        {FILTERS.map((filter) => (
          <ToggleChip
            key={filter.value}
            active={status === filter.value}
            onClick={() => setStatus(filter.value)}
          >
            {t(filter.labelKey)}
          </ToggleChip>
        ))}
      </div>

      {concepts.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2 py-6"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.courseDetail.brain.concepts.title")}
        </p>
      ) : concepts.isError ? (
        <p role="alert" className="text-body text-destructive py-6">
          {concepts.error.message}
        </p>
      ) : concepts.data.length === 0 ? (
        <p className="text-body text-muted-foreground py-6">
          {t("spaces.courseDetail.brain.concepts.empty")}
        </p>
      ) : (
        <ul className="border-border-subtle divide-border-subtle mt-1 flex flex-col divide-y">
          {concepts.data.map((concept) => (
            <li key={concept.id}>
              <button
                type="button"
                onClick={() => onSelect(concept)}
                aria-current={selectedId === concept.id || undefined}
                className={cn(
                  "flex w-full min-w-0 cursor-pointer items-center gap-3 rounded-sm px-2 py-2 text-left",
                  selectedId === concept.id
                    ? "bg-surface-strong"
                    : "hover:bg-surface-subtle",
                )}
              >
                <span className="text-body text-ink min-w-0 flex-1 truncate">
                  {concept.canonical_name}
                </span>
                {concept.status === "CANDIDATE" ? (
                  <span className="text-label text-warning-foreground bg-warning-soft shrink-0 rounded-xs px-2 py-0.5">
                    {t("spaces.courseDetail.brain.status.CANDIDATE")}
                  </span>
                ) : null}
                {concept.stale_archivable ? (
                  <span className="text-label text-ink-muted shrink-0">
                    {t("spaces.courseDetail.brain.concepts.staleArchivable")}
                  </span>
                ) : null}
                <span className="text-label text-ink-muted shrink-0 tabular-nums">
                  {t("spaces.courseDetail.brain.concepts.occurrences", {
                    count: concept.occurrence_count,
                  })}
                  {" · "}
                  {t("spaces.courseDetail.brain.concepts.records", {
                    count: concept.record_count,
                  })}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
