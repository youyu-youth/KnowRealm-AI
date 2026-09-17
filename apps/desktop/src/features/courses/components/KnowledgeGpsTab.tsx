import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  ConceptMastery,
  CourseDetail,
  MasteryStatus,
} from "@/features/courses/api/types";
import { useCourseMastery } from "@/features/courses/api/queries";
import { ConceptMasteryDetailDialog } from "@/features/courses/components/ConceptMasteryDetailDialog";
import { ConceptMasteryList } from "@/features/courses/components/ConceptMasteryList";
import { MasteryStatusCounts } from "@/features/courses/components/MasteryStatusCounts";
import {
  isMasteryStatus,
  masteryStatusLabelKeys,
  masteryStatuses,
} from "@/features/courses/masteryStatus";

const ALL_FILTER = "ALL";

/** 知识GPS：真实 Concept Mastery 列表 + 状态筛选（URL 可恢复）；行可下钻详情。 */
export function KnowledgeGpsTab({
  course,
  statusFilter,
  onStatusFilterChange,
  onOpenBrain,
}: {
  course: CourseDetail;
  statusFilter?: MasteryStatus;
  onStatusFilterChange: (status?: MasteryStatus) => void;
  onOpenBrain: () => void;
}) {
  const { t } = useTranslation();
  const mastery = useCourseMastery(course.id, statusFilter);
  const [selectedConcept, setSelectedConcept] = useState<ConceptMastery | null>(
    null,
  );
  const filterItems = [
    { value: ALL_FILTER, label: t("spaces.courseDetail.gps.filterAll") },
    ...masteryStatuses.map((status) => ({
      value: status,
      label: t(masteryStatusLabelKeys[status]),
    })),
  ];

  return (
    <SurfaceCard title={t("spaces.courseDetail.gps.tabTitle")}>
      {mastery.isPending ? (
        <p
          role="status"
          className="text-body text-ink-muted mt-4 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.courseDetail.gps.loading")}
        </p>
      ) : null}

      {mastery.isError ? (
        <div className="mt-4 flex flex-col items-start gap-3">
          <p className="text-body text-ink-strong">
            {t("spaces.courseDetail.gps.errorTitle")}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void mastery.refetch()}
          >
            {t("spaces.courseDetail.gps.retry")}
          </Button>
        </div>
      ) : null}

      {mastery.data ? (
        mastery.data.confirmed_concept_count === 0 ? (
          <div className="mt-4 flex flex-col items-start gap-2">
            <p className="text-body text-ink-strong">
              {t("spaces.courseDetail.gps.emptyTitle")}
            </p>
            <p className="text-label text-ink-muted">
              {t("spaces.courseDetail.gps.emptyDescription")}
            </p>
            <Button variant="outline" size="sm" onClick={onOpenBrain}>
              {t("spaces.courseDetail.gps.emptyAction")}
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex min-w-0 flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <MasteryStatusCounts
                counts={mastery.data.status_counts}
                className="flex flex-wrap items-center gap-x-4 gap-y-2"
              />
              <p className="text-label text-ink-muted">
                {t("spaces.courseDetail.gps.coverage")}{" "}
                <span className="text-ink-strong tabular-nums">
                  {t("spaces.courseDetail.gps.coverageValue", {
                    verified: mastery.data.verified_concept_count,
                    total: mastery.data.confirmed_concept_count,
                  })}
                </span>
              </p>
            </div>

            <div className="flex min-w-0 items-center justify-between gap-3">
              <h3 className="text-label text-ink-muted">
                {t("spaces.courseDetail.gps.conceptListLabel")}
              </h3>
              <Select
                items={filterItems}
                value={statusFilter ?? ALL_FILTER}
                onValueChange={(value) =>
                  onStatusFilterChange(
                    isMasteryStatus(value) ? value : undefined,
                  )
                }
              >
                <SelectTrigger
                  size="sm"
                  className="bg-background w-36"
                  aria-label={t("spaces.courseDetail.gps.filterLabel")}
                >
                  <SelectValue>
                    {statusFilter
                      ? t(masteryStatusLabelKeys[statusFilter])
                      : t("spaces.courseDetail.gps.filterAll")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {filterItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            {mastery.data.concepts.length === 0 ? (
              <p className="text-body text-ink-muted">
                {t("spaces.courseDetail.gps.filterEmpty")}
              </p>
            ) : (
              <ConceptMasteryList
                concepts={mastery.data.concepts}
                onSelect={setSelectedConcept}
              />
            )}
          </div>
        )
      ) : null}

      <ConceptMasteryDetailDialog
        courseId={course.id}
        concept={selectedConcept}
        open={selectedConcept !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedConcept(null);
        }}
      />
    </SurfaceCard>
  );
}
