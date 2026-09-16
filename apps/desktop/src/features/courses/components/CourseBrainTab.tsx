import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag, type StatusTagProps } from "@/components/common/StatusTag";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { ToggleChip } from "@/components/common/ToggleChip";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  useCourseBrainConcepts,
  useCourseBrainView,
  useTriggerBuild,
  type CourseBrainPhase,
} from "@/features/courses/api/courseBrain";
import type { BrainConcept, CourseDetail } from "@/features/courses/api/types";
import { CourseBrainConceptDetail } from "@/features/courses/components/CourseBrainConceptDetail";
import { CourseBrainConceptList } from "@/features/courses/components/CourseBrainConceptList";
import { CourseBrainCreateConceptSheet } from "@/features/courses/components/CourseBrainCreateConceptSheet";
import { CourseBrainGraph } from "@/features/courses/components/CourseBrainGraph";
import { CourseBrainRelationReview } from "@/features/courses/components/CourseBrainRelationReview";
import { CourseBrainReviewDrawer } from "@/features/courses/components/CourseBrainReviewDrawer";

type BrainMode = "graph" | "list";

const STATUS_TONES: Record<CourseBrainPhase, StatusTagProps["tone"]> = {
  EMPTY: "neutral",
  BUILDING: "neutral",
  REVIEW: "warning",
  READY: "success",
  STALE: "warning",
  FAILED: "danger",
};

function formatBuiltAt(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

/** 课程脑图标签页：Course Brain 主页面（状态栏 + 图谱/列表双视图 + 概念详情）。 */
export function CourseBrainTab({ course }: { course: CourseDetail }) {
  const { t, i18n } = useTranslation();
  const view = useCourseBrainView(course.id);
  const triggerBuild = useTriggerBuild(course.id);
  // limit 200 = 后端上限；图谱节点点击要在此列表里映射完整概念。
  const confirmed = useCourseBrainConcepts(course.id, {
    status: "CONFIRMED",
    limit: 200,
  });
  const [mode, setMode] = useState<BrainMode>("graph");
  const [selected, setSelected] = useState<BrainConcept | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // 图谱节点全为 CONFIRMED 概念：从正式列表映射出完整概念（详情需要描述等字段）。
  const handleNodeSelect = useCallback(
    (conceptId: string) => {
      const found = confirmed.data?.find((concept) => concept.id === conceptId);
      if (found) setSelected(found);
    },
    [confirmed.data],
  );

  if (view.phase === "loading") {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2 py-6"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.detail.loading")}
      </p>
    );
  }
  if (view.phase === "error") {
    return (
      <div className="flex flex-col items-start gap-3 py-6">
        <p role="alert" className="text-body text-destructive">
          {t("spaces.detail.errorDescription")}
        </p>
        <Button variant="outline" onClick={view.retry}>
          {t("spaces.detail.retry")}
        </Button>
      </div>
    );
  }

  const { snapshot } = view;
  const statusLabel = t(`spaces.courseDetail.brain.status.${snapshot.status}`);
  const buildPending = triggerBuild.isPending;
  const showWorkspace =
    snapshot.status === "READY" ||
    snapshot.status === "REVIEW" ||
    snapshot.status === "STALE";

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <header className="border-border-subtle flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <h2 className="text-section font-section text-ink-strong shrink-0">
            {t("spaces.detail.tabs.map")}
          </h2>
          <StatusTag tone={STATUS_TONES[snapshot.status]}>
            {statusLabel}
          </StatusTag>
          <p className="text-label text-ink-muted min-w-0">
            {t(`spaces.courseDetail.brain.statusHint.${snapshot.status}`)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {snapshot.last_built_at ? (
            <span className="text-label text-ink-muted tabular-nums">
              {t("spaces.courseDetail.brain.build.lastBuiltAt", {
                time: formatBuiltAt(snapshot.last_built_at, i18n.language),
              })}
            </span>
          ) : null}
          {snapshot.status === "BUILDING" ? (
            <Button size="sm" disabled aria-live="polite">
              <Spinner aria-hidden="true" data-icon="inline-start" />
              {t("spaces.courseDetail.brain.build.building")}
            </Button>
          ) : null}
          {snapshot.status === "STALE" || snapshot.status === "FAILED" ? (
            <Button
              size="sm"
              disabled={buildPending}
              onClick={() => triggerBuild.mutate()}
            >
              {buildPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {t(
                snapshot.status === "FAILED"
                  ? "spaces.courseDetail.brain.build.retry"
                  : "spaces.courseDetail.brain.build.rebuild",
              )}
            </Button>
          ) : null}
        </div>
      </header>

      {snapshot.status === "EMPTY" ? (
        <SurfaceCard title={t("spaces.courseDetail.brain.emptyGuide.title")}>
          <div className="flex flex-col items-start gap-4">
            <p className="text-body-dense text-ink-muted max-w-reading mt-1">
              {t("spaces.courseDetail.brain.emptyGuide.description")}
            </p>
            <Button
              disabled={buildPending}
              onClick={() => triggerBuild.mutate()}
            >
              {buildPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {t("spaces.courseDetail.brain.emptyGuide.cta")}
            </Button>
          </div>
        </SurfaceCard>
      ) : null}

      {snapshot.status === "BUILDING" ? (
        <SurfaceCard title={t("spaces.courseDetail.brain.graph.title")}>
          <p className="text-body text-muted-foreground py-10 text-center">
            {t("spaces.courseDetail.brain.graph.empty")}
          </p>
        </SurfaceCard>
      ) : null}

      {showWorkspace ? (
        <>
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div
              role="group"
              aria-label={t("spaces.courseDetail.brain.graph.title")}
              className="flex items-center gap-1"
            >
              {(["graph", "list"] as const).map((value) => (
                <ToggleChip
                  key={value}
                  active={mode === value}
                  onClick={() => setMode(value)}
                >
                  {t(`spaces.courseDetail.brain.view.${value}`)}
                </ToggleChip>
              ))}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {snapshot.candidate_count > 0 ? (
                <Button size="sm" onClick={() => setReviewOpen(true)}>
                  {t("spaces.courseDetail.brain.review.open", {
                    count: snapshot.candidate_count,
                  })}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCreateOpen(true)}
              >
                {t("spaces.courseDetail.brain.create.action")}
              </Button>
            </div>
          </div>

          <div className="grid min-w-0 gap-5 @2xl:grid-cols-[minmax(0,1fr)_clamp(16rem,22vw,20rem)]">
            <div className="min-w-0">
              {mode === "graph" ? (
                <SurfaceCard title={t("spaces.courseDetail.brain.graph.title")}>
                  {snapshot.graph.nodes.length === 0 ? (
                    <p className="text-body text-muted-foreground py-10 text-center">
                      {t("spaces.courseDetail.brain.graph.empty")}
                    </p>
                  ) : (
                    <CourseBrainGraph
                      courseName={course.name}
                      graph={snapshot.graph}
                      onSelect={handleNodeSelect}
                      className="mt-2"
                    />
                  )}
                </SurfaceCard>
              ) : (
                <SurfaceCard
                  title={t("spaces.courseDetail.brain.concepts.title")}
                >
                  <CourseBrainConceptList
                    courseId={course.id}
                    selectedId={selected?.id ?? null}
                    onSelect={setSelected}
                    className="mt-2"
                  />
                </SurfaceCard>
              )}
            </div>
            <aside className="border-border-subtle min-w-0 border-t pt-4 @2xl:border-t-0 @2xl:border-l @2xl:pl-5">
              {selected ? (
                <CourseBrainConceptDetail
                  courseId={course.id}
                  concept={selected}
                  onClose={() => setSelected(null)}
                />
              ) : (
                <p className="text-label text-ink-muted">
                  {t("spaces.courseDetail.brain.detail.placeholder")}
                </p>
              )}
            </aside>
          </div>

          <CourseBrainRelationReview courseId={course.id} />

          <CourseBrainReviewDrawer
            courseId={course.id}
            open={reviewOpen}
            onOpenChange={setReviewOpen}
            onReviewed={() => setSelected(null)}
          />
          <CourseBrainCreateConceptSheet
            courseId={course.id}
            open={createOpen}
            onOpenChange={setCreateOpen}
          />
        </>
      ) : null}
    </div>
  );
}
