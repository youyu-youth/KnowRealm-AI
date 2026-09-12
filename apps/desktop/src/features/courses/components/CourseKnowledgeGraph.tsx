import { Maximize2 } from "lucide-react";
import type { TFunction } from "i18next";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { prefersReducedMotion, rootFontSize } from "@/charts/dom";
import type { echarts } from "@/charts/echarts";
import { chartPalette, cssVar, darkTooltipStyle } from "@/charts/token";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  aggregateCourseKnowledgePoints,
  buildCourseKnowledgeRelations,
  mockCourseKnowledgePoints,
  translateNodeName,
  type AggregatedCourseKnowledgePoint,
} from "@/features/courses/courseDetailInsights";
import { cn } from "@/lib/utils";

type GraphVariant = "rose" | "relation";

type DisplayPoint = AggregatedCourseKnowledgePoint & { displayName: string };

type CourseKnowledgeGraphProps = {
  course: CourseDetail;
  variant: GraphVariant;
  /** 卡片标题的 i18n key（默认「知识概念图谱」）。 */
  titleKey?: string;
  /** 图表区高度类（rem 基准，随字号缩放）。 */
  heightClass?: string;
  className?: string;
};

type TooltipParams = {
  data?: {
    name?: string;
    value?: number;
    totalWeight?: number;
    recordCount?: number;
    core?: boolean;
  };
};

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function chartGrayRamp() {
  const palette = chartPalette();
  return [
    palette.primary ?? "#1a1c20",
    palette.foreground ?? "#2f3239",
    palette.neutralForeground ?? "#4b4f58",
    palette.mutedForeground ?? "#666b75",
    palette.faintForeground ?? "#858b96",
    palette.borderStrong ?? "#bbc0c9",
  ];
}

function buildRoseOption(
  points: DisplayPoint[],
  t: TFunction,
): echarts.EChartsCoreOption {
  const palette = chartPalette();
  const colors = chartGrayRamp();
  const reducedMotion = prefersReducedMotion();
  const fontSize = Math.round(rootFontSize() * 0.75);

  return {
    animation: !reducedMotion,
    animationDuration: reducedMotion ? 0 : 420,
    animationEasing: "cubicOut",
    tooltip: {
      ...darkTooltipStyle(),
      trigger: "item",
      renderMode: "richText",
      confine: true,
      formatter: ({ data }: TooltipParams) => {
        if (!data?.name) return "";
        return [
          data.name,
          t("spaces.courseDetail.graph.weightValue", {
            weight: data.value ?? 0,
          }),
          t("spaces.courseDetail.graph.sourceRecords", {
            count: data.recordCount ?? 0,
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
          formatter: ({ name }: { name?: string }) => truncate(name ?? "", 10),
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
        data: points.map((point, index) => {
          const colorIndex = Math.round(
            (index / Math.max(points.length - 1, 1)) * (colors.length - 1),
          );
          return {
            name: point.displayName,
            value: point.totalWeight,
            recordCount: point.recordCount,
            itemStyle: {
              color: point.other
                ? (palette.borderStrong ?? colors[colors.length - 1])
                : colors[colorIndex],
            },
          };
        }),
      },
    ],
  };
}

function buildRelationOption(
  courseName: string,
  points: DisplayPoint[],
  t: TFunction,
): echarts.EChartsCoreOption {
  const palette = chartPalette();
  const colors = chartGrayRamp();
  const reducedMotion = prefersReducedMotion();
  const fontSize = Math.round(rootFontSize() * 0.75);
  const visiblePoints = points.filter((point) => !point.other);
  const maxWeight = Math.max(
    ...visiblePoints.map((point) => point.totalWeight),
  );
  const coreId = "course-core";
  const sharedTagLinks = buildCourseKnowledgeRelations(visiblePoints).map(
    (relation) => ({
      source: relation.source,
      target: relation.target,
      value: relation.sharedTagCount,
      lineStyle: {
        width: relation.sharedTagCount > 1 ? 1.25 : 0.75,
        opacity: relation.sharedTagCount > 1 ? 0.52 : 0.3,
      },
    }),
  );

  return {
    animation: !reducedMotion,
    animationDuration: reducedMotion ? 0 : 360,
    animationDurationUpdate: reducedMotion ? 0 : 240,
    animationEasing: "cubicOut",
    animationEasingUpdate: "cubicOut",
    tooltip: {
      ...darkTooltipStyle(),
      trigger: "item",
      renderMode: "richText",
      confine: true,
      formatter: ({ data }: TooltipParams) => {
        if (!data?.name) return "";
        if (data.core) return data.name;
        return [
          data.name,
          t("spaces.courseDetail.graph.weightValue", {
            weight: data.totalWeight ?? 0,
          }),
          t("spaces.courseDetail.graph.sourceRecords", {
            count: data.recordCount ?? 0,
          }),
        ].join("\n");
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        scaleLimit: { min: 0.7, max: 3 },
        draggable: true,
        cursor: "grab",
        labelLayout: { hideOverlap: true },
        label: {
          show: true,
          position: "right",
          distance: 5,
          color: palette.foreground,
          fontSize,
          formatter: ({ name }: { name?: string }) => truncate(name ?? "", 12),
        },
        data: [
          {
            id: coreId,
            name: courseName,
            core: true,
            symbolSize: 48,
            itemStyle: { color: palette.primary, borderWidth: 0 },
            label: {
              color: cssVar("--paper"),
              fontWeight: 600,
              position: "inside",
              width: 40,
              overflow: "truncate",
              formatter: () => truncate(courseName, 7),
            },
          },
          ...visiblePoints.map((point, index) => {
            const colorIndex = Math.round(
              (index / Math.max(visiblePoints.length - 1, 1)) *
                (colors.length - 1),
            );
            return {
              id: point.id,
              name: point.displayName,
              totalWeight: point.totalWeight,
              recordCount: point.recordCount,
              symbolSize: 14 + Math.round((point.totalWeight / maxWeight) * 20),
              itemStyle: {
                color: colors[colorIndex],
                borderColor: palette.card,
                borderWidth: 1.5,
              },
            };
          }),
        ],
        links: [
          ...visiblePoints.map((point) => ({
            source: coreId,
            target: point.id,
            lineStyle: { width: 1, opacity: 0.48 },
          })),
          ...sharedTagLinks,
        ],
        force: {
          edgeLength: [54, 92],
          repulsion: 150,
          gravity: 0.08,
          friction: 0.62,
          layoutAnimation: !reducedMotion,
        },
        lineStyle: {
          color: palette.borderStrong,
          width: 1,
          opacity: 0.4,
          curveness: 0.12,
        },
        emphasis: {
          focus: "adjacency",
          blurScope: "coordinateSystem",
          lineStyle: { color: palette.foreground, opacity: 0.82, width: 1.5 },
        },
      },
    ],
  };
}

export function CourseKnowledgeGraph({
  course,
  variant,
  titleKey = "spaces.courseDetail.graph.title",
  heightClass = "h-72",
  className,
}: CourseKnowledgeGraphProps) {
  const { t } = useTranslation();
  const [fullscreen, setFullscreen] = useState(false);
  const sourcePoints = useMemo(
    () => mockCourseKnowledgePoints(course),
    [course],
  );
  const points = useMemo<DisplayPoint[]>(
    () =>
      aggregateCourseKnowledgePoints(sourcePoints).map((point) => ({
        ...point,
        displayName: translateNodeName(t, point),
      })),
    [sourcePoints, t],
  );
  const option = useMemo(
    () =>
      variant === "rose"
        ? buildRoseOption(points, t)
        : buildRelationOption(course.name, points, t),
    [variant, points, course.name, t],
  );
  const namedPoints = points.filter((point) => !point.other);
  const summaryPoints = variant === "rose" ? points : namedPoints;
  const conceptCount =
    variant === "rose"
      ? points.reduce((total, point) => total + point.conceptCount, 0)
      : namedPoints.length;
  const totalWeight = points.reduce(
    (total, point) => total + point.totalWeight,
    0,
  );
  const recordCount = new Set(sourcePoints.map((point) => point.recordId)).size;
  const ariaLabel = t(
    variant === "rose"
      ? "spaces.courseDetail.graph.roseAria"
      : "spaces.courseDetail.graph.relationAria",
    { course: course.name },
  );

  return (
    <SurfaceCard
      title={t(titleKey)}
      sample
      className={cn("@container", className)}
      action={
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label={t("spaces.courseDetail.graph.fullscreen")}
          onClick={() => setFullscreen(true)}
        >
          <Maximize2 data-icon="inline-start" aria-hidden="true" />
          <span className="max-compact:sr-only">
            {t("spaces.courseDetail.graph.fullscreen")}
          </span>
        </Button>
      }
    >
      <div className="mt-2 flex min-w-0 flex-col gap-5 @2xl:flex-row @2xl:items-start">
        <div
          className={cn(
            "w-full min-w-0 @2xl:flex-1",
            variant === "rose" && "@2xl:max-w-[26rem]",
          )}
        >
          <div className={cn("view-switch-enter", heightClass)}>
            <BaseChart
              option={option}
              ariaLabel={ariaLabel}
              className="h-full w-full"
            />
          </div>
        </div>
        <div className="@2xl:border-border-subtle min-w-0 flex-1 @2xl:border-l @2xl:pl-5">
          <p className="text-label text-ink-muted">
            {t("spaces.courseDetail.graph.weightSummary")}
          </p>
          <dl className="mt-2 grid grid-cols-3 gap-3">
            <div>
              <dt className="text-label text-ink-muted">
                {t("spaces.courseDetail.graph.summaryConcepts")}
              </dt>
              <dd className="text-body text-ink-strong mt-0.5 font-medium tabular-nums">
                {conceptCount}
              </dd>
            </div>
            <div>
              <dt className="text-label text-ink-muted">
                {t("spaces.courseDetail.graph.summaryWeight")}
              </dt>
              <dd className="text-body text-ink-strong mt-0.5 font-medium tabular-nums">
                {totalWeight}
              </dd>
            </div>
            <div>
              <dt className="text-label text-ink-muted">
                {t("spaces.courseDetail.graph.summaryRecords")}
              </dt>
              <dd className="text-body text-ink-strong mt-0.5 font-medium tabular-nums">
                {recordCount}
              </dd>
            </div>
          </dl>
          <p className="text-label text-ink-muted mt-4">
            {t("spaces.courseDetail.graph.conceptCount", {
              count: conceptCount,
            })}
          </p>
          <ul className="divide-border-subtle mt-1 flex flex-col divide-y">
            {summaryPoints.map((point) => (
              <li
                key={point.id}
                className="flex min-w-0 items-center justify-between gap-3 py-1.5"
              >
                <span
                  className="text-body-dense text-ink min-w-0 truncate"
                  title={point.displayName}
                >
                  {point.displayName}
                </span>
                <span className="text-label text-ink-muted shrink-0 tabular-nums">
                  {t("spaces.courseDetail.graph.weightCompact", {
                    weight: point.totalWeight,
                    count: point.recordCount,
                  })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent className="sm:max-w-5xl">
          <DialogHeader>
            <DialogTitle>{t(titleKey)}</DialogTitle>
            <DialogDescription>
              {t("spaces.courseDetail.graph.fullscreenDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="mx-auto h-[68vh] w-full max-w-3xl">
            <BaseChart
              option={option}
              ariaLabel={ariaLabel}
              className="h-full w-full"
            />
          </div>
        </DialogContent>
      </Dialog>
    </SurfaceCard>
  );
}
