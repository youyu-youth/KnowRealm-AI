import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { appToast } from "@/components/common/appToastManager";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { ToggleChip } from "@/components/common/ToggleChip";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  BRAIN_PAGE_LIMIT,
  useApplyReview,
  useCourseBrainRelations,
} from "@/features/courses/api/courseBrain";
import type { BrainRelationStatus } from "@/features/courses/api/types";

type RelationFilter = Extract<BrainRelationStatus, "CANDIDATE" | "CONFIRMED">;

const FILTERS: { value: RelationFilter; labelKey: string }[] = [
  {
    value: "CANDIDATE",
    labelKey: "spaces.courseDetail.brain.review.filterCandidate",
  },
  {
    value: "CONFIRMED",
    labelKey: "spaces.courseDetail.brain.review.filterConfirmed",
  },
];

/**
 * Relation 审核区：候选关系逐条确认 / 忽略；已确认视图展示过期徽章
 * （stale = 最近一次成功构建零证据支撑，仅展示不自动降级）。
 */
export function CourseBrainRelationReview({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<RelationFilter>("CANDIDATE");
  const relations = useCourseBrainRelations(courseId, {
    status: filter,
    limit: BRAIN_PAGE_LIMIT,
  });
  const applyReview = useApplyReview(courseId);

  function decide(
    relationId: string,
    decision: "confirm_relation" | "dismiss_relation",
  ) {
    applyReview.mutate(
      { decisions: [{ decision_type: decision, relation_id: relationId }] },
      {
        onSuccess: () => {
          appToast.add({
            description: t("spaces.courseDetail.brain.review.relationApplied", {
              action:
                decision === "confirm_relation"
                  ? t("spaces.courseDetail.brain.review.confirmedWord")
                  : t("spaces.courseDetail.brain.review.dismissedWord"),
            }),
          });
        },
      },
    );
  }

  const pending = applyReview.isPending;

  return (
    <SurfaceCard title={t("spaces.courseDetail.brain.review.relationTitle")}>
      <div className="flex min-w-0 flex-col gap-3">
        <div
          role="group"
          aria-label={t("spaces.courseDetail.brain.review.relationTitle")}
          className="flex items-center gap-1"
        >
          {FILTERS.map((option) => (
            <ToggleChip
              key={option.value}
              active={filter === option.value}
              onClick={() => setFilter(option.value)}
            >
              {t(option.labelKey)}
            </ToggleChip>
          ))}
        </div>

        {applyReview.isError ? (
          <p role="alert" className="text-body text-destructive">
            {applyReview.error.message}
          </p>
        ) : null}

        {relations.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2 py-4"
          >
            <Spinner aria-hidden="true" />
            {t("spaces.courseDetail.brain.review.loadingRelations")}
          </p>
        ) : relations.isError ? (
          <p role="alert" className="text-body text-destructive py-4">
            {relations.error.message}
          </p>
        ) : (relations.data?.length ?? 0) === 0 ? (
          <p className="text-body text-muted-foreground py-4">
            {t(
              filter === "CANDIDATE"
                ? "spaces.courseDetail.brain.review.relationEmpty"
                : "spaces.courseDetail.brain.review.confirmedRelationEmpty",
            )}
          </p>
        ) : (
          // 局部滚动：关系多时不撑破固定工作区（DESIGN.md §4）。
          <ul className="border-border-subtle divide-border-subtle flex max-h-96 min-w-0 flex-col divide-y overflow-y-auto">
            {relations.data.map((relation) => (
              <li
                key={relation.id}
                className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 py-2"
              >
                <span className="text-body-dense text-ink flex min-w-0 items-center gap-1.5">
                  <span className="min-w-0 truncate">
                    {relation.source_name}
                  </span>
                  <span aria-hidden="true" className="text-ink-muted shrink-0">
                    →
                  </span>
                  <span className="min-w-0 truncate">
                    {relation.target_name}
                  </span>
                </span>
                <StatusTag className="shrink-0">
                  {t(
                    `spaces.courseDetail.brain.relationType.${relation.relation_type}`,
                    {
                      defaultValue: relation.relation_type,
                    },
                  )}
                </StatusTag>
                {relation.stale ? (
                  <StatusTag tone="warning" className="shrink-0">
                    {t("spaces.courseDetail.brain.review.staleBadge")}
                  </StatusTag>
                ) : null}
                <span className="text-label text-ink-muted shrink-0 tabular-nums">
                  {t("spaces.courseDetail.brain.review.confidence", {
                    value: relation.confidence.toFixed(2),
                  })}
                </span>
                <span className="ml-auto flex shrink-0 items-center gap-1 pl-2">
                  {filter === "CANDIDATE" ? (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={pending}
                        onClick={() => decide(relation.id, "confirm_relation")}
                      >
                        {t("spaces.courseDetail.brain.review.confirmRelation")}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={pending}
                        onClick={() => decide(relation.id, "dismiss_relation")}
                      >
                        {t("spaces.courseDetail.brain.review.dismissRelation")}
                      </Button>
                    </>
                  ) : (
                    <span className="text-label text-ink-muted">
                      {t("spaces.courseDetail.brain.review.evidenceCount", {
                        count: relation.evidence_count,
                      })}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </SurfaceCard>
  );
}
