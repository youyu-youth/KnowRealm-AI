import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { prefersReducedMotion, rootFontSize } from "@/charts/dom";
import type { echarts } from "@/charts/echarts";
import { chartPalette, darkTooltipStyle } from "@/charts/token";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { BrainConcept } from "@/features/courses/api/types";
import {
  useCourseBrainConcepts,
  useCourseBrainView,
  useTriggerBuild,
} from "@/features/courses/api/courseBrain";
import type { CourseDetail } from "@/features/courses/api/types";

// 玫瑰图展示 Top N 概念（后端已按重要度降序返回），瓣数更多会挤压标签可读性。
const ROSE_TOP_N = 8;

type RoseTooltipParams = {
  data?: {
    name?: string;
    importance?: number;
    occurrenceCount?: number;
    recordCount?: number;
  };
};

function buildRoseOption(
  concepts: BrainConcept[],
  t: ReturnType<typeof useTranslation>["t"],
): echarts.EChartsCoreOption {
  const palette = chartPalette();
  const reducedMotion = prefersReducedMotion();
  const fontSize = Math.round(rootFontSize() * 0.75);
  const grays = [
    palette.primary ?? "#1A1C20",
    palette.foreground ?? "#2F3239",
    palette.neutralForeground ?? "#4B4F58",
    palette.mutedForeground ?? "#666B75",
    palette.faintForeground ?? "#858B96",
    palette.borderStrong ?? "#BBC0C9",
  ];

  return {
    animation: !reducedMotion,
    animationDuration: reducedMotion ? 0 : 420,
    animationEasing: "cubicOut",
    tooltip: {
      ...darkTooltipStyle(),
      trigger: "item",
      renderMode: "richText",
      confine: true,
      formatter: ({ data }: RoseTooltipParams) => {
        if (!data?.name) return "";
        return [
          data.name,
          t("spaces.courseDetail.brain.graph.tooltipImportance", {
            importance: data.importance ?? 0,
          }),
          t("spaces.courseDetail.brain.concepts.occurrences", {
            count: data.occurrenceCount ?? 0,
          }),
        ].join("\n");
      },
    },
    series: [
      {
        type: "pie",
        roseType: "radius",
        radius: ["18%", "72%"],
        center: ["50%", "50%"],
        minAngle: 7,
        avoidLabelOverlap: true,
        animationType: "scale",
        labelLayout: { hideOverlap: true },
        label: {
          show: true,
          color: palette.foreground,
          fontSize,
          formatter: ({ name }: { name?: string }) =>
            (name ?? "").length > 10 ? `${(name ?? "").slice(0, 9)}…` : name,
        },
        labelLine: {
          show: true,
          length: 8,
          length2: 6,
          smooth: 0.2,
          lineStyle: { color: palette.borderStrong, width: 1 },
        },
        itemStyle: {
          borderColor: palette.card,
          borderWidth: 2,
          borderRadius: 2,
        },
        emphasis: {
          scale: true,
          scaleSize: 4,
          itemStyle: { borderColor: palette.primary, borderWidth: 2 },
        },
        data: concepts.map((concept, index) => ({
          name: concept.canonical_name,
          value: concept.occurrence_count,
          importance: concept.importance,
          occurrenceCount: concept.occurrence_count,
          recordCount: concept.record_count,
          itemStyle: {
            color:
              grays[
                Math.round(
                  (index / Math.max(concepts.length - 1, 1)) *
                    (grays.length - 1),
                )
              ],
          },
        })),
      },
    ],
  };
}

type CourseBrainRoseCardProps = {
  course: CourseDetail;
  className?: string;
};

/** 概览 Tab 概念分布卡：真实 Concept Top 分布玫瑰图；未就绪时给构建引导空态。 */
export function CourseBrainRoseCard({
  course,
  className,
}: CourseBrainRoseCardProps) {
  const { t } = useTranslation();
  const view = useCourseBrainView(course.id);
  const triggerBuild = useTriggerBuild(course.id);
  const concepts = useCourseBrainConcepts(course.id, { status: "CONFIRMED" });
  // 后端已按重要度降序；同重要度内再按出现次数取 Top（工单：importance/证据排序）。
  const top = useMemo(
    () =>
      [...(concepts.data ?? [])]
        .sort(
          (left, right) =>
            right.importance - left.importance ||
            right.occurrence_count - left.occurrence_count,
        )
        .slice(0, ROSE_TOP_N),
    [concepts.data],
  );
  const option = useMemo(
    () => (top.length > 0 ? buildRoseOption(top, t) : null),
    [top, t],
  );
  const ariaLabel = t("spaces.courseDetail.brain.rose.aria", {
    course: course.name,
  });

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.brain.rose.title")}
      className={className}
    >
      {view.phase === "loading" || concepts.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2 py-8"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.courseDetail.brain.rose.title")}
        </p>
      ) : view.phase === "error" ? (
        <p role="alert" className="text-body text-destructive py-8">
          {t("spaces.detail.errorDescription")}
        </p>
      ) : concepts.isError ? (
        <p role="alert" className="text-body text-destructive py-8">
          {concepts.error.message}
        </p>
      ) : option ? (
        <div className="mt-2 flex min-w-0 flex-col gap-5 @2xl:flex-row @2xl:items-start">
          <div className="h-72 w-full min-w-0 @2xl:max-w-[24rem]">
            <BaseChart
              option={option}
              ariaLabel={ariaLabel}
              className="h-full w-full"
            />
          </div>
          <div className="@2xl:border-border-subtle min-w-0 flex-1 @2xl:border-l @2xl:pl-5">
            <ul className="divide-border-subtle flex flex-col divide-y">
              {top.map((concept) => (
                <li
                  key={concept.id}
                  className="flex min-w-0 items-center justify-between gap-3 py-1.5"
                >
                  <span
                    className="text-body-dense text-ink min-w-0 truncate"
                    title={concept.canonical_name}
                  >
                    {concept.canonical_name}
                  </span>
                  <span className="text-label text-ink-muted shrink-0 tabular-nums">
                    {t("spaces.courseDetail.brain.concepts.occurrences", {
                      count: concept.occurrence_count,
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-start gap-4 py-2">
          <p className="text-body-dense text-ink-muted max-w-reading">
            {(concepts.data ?? []).length === 0
              ? t("spaces.courseDetail.brain.emptyGuide.description")
              : t("spaces.courseDetail.brain.graph.empty")}
          </p>
          {view.phase === "REVIEW" ? null : view.phase === "BUILDING" ? (
            <Button size="sm" disabled aria-live="polite">
              <Spinner aria-hidden="true" data-icon="inline-start" />
              {t("spaces.courseDetail.brain.build.building")}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={triggerBuild.isPending}
              onClick={() => triggerBuild.mutate()}
            >
              {triggerBuild.isPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {t(
                view.phase === "EMPTY"
                  ? "spaces.courseDetail.brain.emptyGuide.cta"
                  : view.phase === "FAILED"
                    ? "spaces.courseDetail.brain.build.retry"
                    : "spaces.courseDetail.brain.build.rebuild",
              )}
            </Button>
          )}
        </div>
      )}
    </SurfaceCard>
  );
}
