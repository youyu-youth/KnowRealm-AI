import { Link } from "@tanstack/react-router";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { ToggleChip } from "@/components/common/ToggleChip";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { BrainConcept } from "@/features/courses/api/types";
import { useConceptSources } from "@/features/courses/api/courseBrain";
import {
  anchorJumpTarget,
  knowledgePointJumpTarget,
} from "@/features/courses/courseBrainJump";
import { formatTimelineTimestamp } from "@/features/records/recordPresentation";

// 筛选值：锚点四类 + 知识点小节；ALL 恒显示。
const KP_FILTER = "KNOWLEDGE_POINT" as const;
type SourceFilter = "ALL" | string;

type CourseBrainConceptDetailProps = {
  courseId: string;
  concept: BrainConcept;
  onClose: () => void;
};

/** 概念详情面板：元信息 + 描述 + 来源列表（锚点四类与知识点，按类型筛选）。 */
export function CourseBrainConceptDetail({
  courseId,
  concept,
  onClose,
}: CourseBrainConceptDetailProps) {
  const { t } = useTranslation();
  const sources = useConceptSources(courseId, concept.id);
  const [filter, setFilter] = useState<SourceFilter>("ALL");

  const sourceTypes = useMemo(() => {
    const types = new Set<string>();
    for (const anchor of sources.data?.anchors ?? []) {
      types.add(anchor.source_type);
    }
    if ((sources.data?.knowledge_points.length ?? 0) > 0) {
      types.add(KP_FILTER);
    }
    return [...types];
  }, [sources.data]);

  const visibleAnchors =
    filter === "ALL"
      ? (sources.data?.anchors ?? [])
      : (sources.data?.anchors ?? []).filter(
          (anchor) => anchor.source_type === filter,
        );
  const visibleKps =
    filter === "ALL" || filter === KP_FILTER
      ? (sources.data?.knowledge_points ?? [])
      : [];

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <header className="flex min-w-0 items-start justify-between gap-3">
        <h3
          className="text-section font-section text-ink-strong min-w-0 truncate"
          title={concept.canonical_name}
        >
          {concept.canonical_name}
        </h3>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={t("spaces.courseDetail.brain.detail.close")}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </Button>
      </header>

      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {concept.status === "CANDIDATE" ? (
          <StatusTag tone="warning">
            {t("spaces.courseDetail.brain.status.CANDIDATE")}
          </StatusTag>
        ) : null}
        <StatusTag>
          {t(`spaces.courseDetail.brain.conceptType.${concept.concept_type}`, {
            defaultValue: concept.concept_type,
          })}
        </StatusTag>
        <StatusTag>
          {t(`spaces.courseDetail.brain.sourceOrigin.${concept.source}`, {
            defaultValue: concept.source,
          })}
        </StatusTag>
        {concept.stale_archivable ? (
          <StatusTag tone="warning">
            {t("spaces.courseDetail.brain.concepts.staleArchivable")}
          </StatusTag>
        ) : null}
      </div>

      <p className="text-label text-ink-muted flex flex-wrap items-center gap-x-3 gap-y-1 tabular-nums">
        <span>
          {t("spaces.courseDetail.brain.graph.tooltipImportance", {
            importance: concept.importance,
          })}
        </span>
        <span>
          {t("spaces.courseDetail.brain.concepts.occurrences", {
            count: concept.occurrence_count,
          })}
        </span>
        <span>
          {t("spaces.courseDetail.brain.concepts.records", {
            count: concept.record_count,
          })}
        </span>
      </p>

      {concept.description ? (
        <p className="text-body-dense text-ink max-w-reading">
          {concept.description}
        </p>
      ) : null}

      {concept.suggested_target_name ? (
        <p className="text-label text-ink-muted">
          {t("spaces.courseDetail.brain.concepts.suggestedMerge", {
            name: concept.suggested_target_name,
          })}
        </p>
      ) : null}

      <section aria-label={t("spaces.courseDetail.brain.sources.title")}>
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          <p className="text-label text-ink-muted mr-1">
            {t("spaces.courseDetail.brain.sources.title")}
          </p>
          {sources.data && sourceTypes.length > 1 ? (
            <>
              <ToggleChip
                active={filter === "ALL"}
                onClick={() => setFilter("ALL")}
              >
                {t("spaces.courseDetail.brain.sources.filterAll")}
              </ToggleChip>
              {sourceTypes.map((type) => (
                <ToggleChip
                  key={type}
                  active={filter === type}
                  onClick={() => setFilter(type)}
                >
                  {t(`spaces.courseDetail.brain.sourceType.${type}`)}
                </ToggleChip>
              ))}
            </>
          ) : null}
        </div>

        {sources.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground mt-3 flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("spaces.courseDetail.brain.sources.title")}
          </p>
        ) : sources.isError ? (
          <p role="alert" className="text-body text-destructive mt-3">
            {sources.error.message}
          </p>
        ) : (sources.data?.anchors.length ?? 0) === 0 &&
          (sources.data?.knowledge_points.length ?? 0) === 0 ? (
          <p className="text-body text-muted-foreground mt-3">
            {t("spaces.courseDetail.brain.sources.empty")}
          </p>
        ) : (
          <ul className="border-border-subtle divide-border-subtle mt-2 flex flex-col divide-y">
            {visibleAnchors.map((anchor) => {
              const jump = anchorJumpTarget(anchor);
              const badge = t(
                `spaces.courseDetail.brain.sourceType.${anchor.source_type}`,
              );
              const quote = anchor.quote?.trim();
              const body = (
                <>
                  <span className="flex min-w-0 items-center gap-2">
                    <StatusTag className="shrink-0">{badge}</StatusTag>
                    {anchor.record_title ? (
                      <span className="text-body-dense text-ink min-w-0 truncate">
                        {anchor.record_title}
                      </span>
                    ) : null}
                    {anchor.source_type === "AUDIO_SEGMENT" &&
                    anchor.start_ms !== null &&
                    anchor.start_ms !== undefined ? (
                      <span className="text-label text-ink-muted shrink-0 tabular-nums">
                        {formatTimelineTimestamp(anchor.start_ms)}
                      </span>
                    ) : null}
                    {anchor.source_type === "DOCUMENT_SEGMENT" &&
                    anchor.page_no !== null &&
                    anchor.page_no !== undefined ? (
                      <span className="text-label text-ink-muted shrink-0 tabular-nums">
                        {t("spaces.courseDetail.brain.sources.page", {
                          page: anchor.page_no,
                        })}
                      </span>
                    ) : null}
                  </span>
                  {quote ? (
                    <span
                      className="text-label text-ink-muted mt-1 line-clamp-2"
                      title={quote}
                    >
                      {quote}
                    </span>
                  ) : null}
                </>
              );
              return (
                <li key={anchor.anchor_id} className="py-2">
                  {jump ? (
                    jump.to === "/chat/$sessionId" ? (
                      <Link
                        to={jump.to}
                        params={jump.params}
                        className="hover:bg-surface-subtle block min-w-0 cursor-pointer rounded-sm px-2 py-1"
                      >
                        {body}
                      </Link>
                    ) : (
                      <Link
                        to={jump.to}
                        params={jump.params}
                        search={jump.search}
                        className="hover:bg-surface-subtle block min-w-0 cursor-pointer rounded-sm px-2 py-1"
                      >
                        {body}
                      </Link>
                    )
                  ) : (
                    <div className="min-w-0 px-2 py-1">{body}</div>
                  )}
                </li>
              );
            })}
            {visibleKps.map((kp) => {
              const jump = knowledgePointJumpTarget(kp);
              return (
                <li key={kp.knowledge_point_id} className="py-2">
                  <Link
                    to={jump.to}
                    params={jump.params}
                    search={jump.search}
                    className="hover:bg-surface-subtle flex min-w-0 cursor-pointer items-center gap-2 rounded-sm px-2 py-1"
                  >
                    <StatusTag className="shrink-0">
                      {t(
                        "spaces.courseDetail.brain.sourceType.KNOWLEDGE_POINT",
                      )}
                    </StatusTag>
                    <span className="text-body-dense text-ink min-w-0 truncate">
                      {kp.knowledge_point_name}
                    </span>
                    <span className="text-label text-ink-muted min-w-0 truncate">
                      {kp.record_title}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
