import { ListTree, Maximize2, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { prefersReducedMotion, rootFontSize } from "@/charts/dom";
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
  mockKnowledgeNodes,
  translateNodeName,
  type KnowledgeNode,
} from "@/features/courses/courseDetailInsights";
import { MasteryStateBadge } from "@/features/courses/components/MasteryStateBadge";
import {
  masteryChartColors,
  masteryDotClassNames,
  masteryStateLabelKeys,
} from "@/features/courses/masteryState";
import { cn } from "@/lib/utils";

type GraphView = "force" | "tree";

type DisplayNode = KnowledgeNode & { displayName: string };

type CourseKnowledgeGraphProps = {
  course: CourseDetail;
  /** 卡片标题的 i18n key（默认「知识概念图谱」）。 */
  titleKey?: string;
  /** 图表区高度类（rem 基准，随字号缩放）。 */
  heightClass?: string;
  className?: string;
};

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

type TooltipParams = {
  data?: { name?: string; core?: boolean; stateLabel?: string };
};

function tooltipConfig() {
  return {
    ...darkTooltipStyle(),
    confine: true,
    formatter: (params: TooltipParams) => {
      const data = params.data;
      if (!data?.name) return "";
      if (data.core) return data.name;
      return `${data.name}<br/>${data.stateLabel ?? ""}`;
    },
  };
}

function buildForceOption(
  courseName: string,
  nodes: DisplayNode[],
  stateLabels: Record<string, string>,
) {
  const palette = chartPalette();
  const stateColors = masteryChartColors();
  const rem = rootFontSize();
  const fontSize = Math.round(rem * 0.75);
  const coreId = nodes.find((node) => node.core)?.id;

  return {
    animation: !prefersReducedMotion(),
    animationDuration: 300,
    tooltip: tooltipConfig(),
    series: [
      {
        type: "graph",
        layout: "none",
        roam: false,
        left: 24,
        right: 24,
        top: 16,
        bottom: 16,
        symbol: "circle",
        data: nodes.map((node) => ({
          id: node.id,
          name: node.displayName,
          core: node.core,
          stateLabel: stateLabels[node.id],
          x: node.x,
          y: node.y,
          symbolSize: node.core ? Math.round(rem * 4.6) : 8,
          itemStyle: {
            color: node.core
              ? (palette.primary ?? "#1a1c20")
              : node.state === "untouched"
                ? palette.card
                : stateColors[node.state],
            borderColor: node.core ? palette.primary : stateColors[node.state],
            borderWidth: node.core ? 0 : node.state === "untouched" ? 1 : 0,
          },
          label: node.core
            ? {
                show: true,
                position: "inside",
                color: cssVar("--paper"),
                fontWeight: 600,
                fontSize: fontSize + 1,
                width: Math.round(rem * 3.9),
                overflow: "truncate",
                formatter: () => truncate(courseName, 8),
              }
            : {
                show: true,
                position: "bottom",
                distance: 5,
                color: palette.foreground,
                fontSize,
                backgroundColor: palette.card,
                borderColor: palette.border,
                borderWidth: 1,
                borderRadius: 4,
                padding: [3, 7],
                formatter: (params: { name?: string }) =>
                  truncate(params.name ?? "", 10),
              },
        })),
        links: nodes
          .filter((node) => !node.core)
          .map((node) => ({ source: coreId, target: node.id })),
        lineStyle: {
          color: palette.borderStrong,
          width: 1,
          curveness: 0.12,
        },
        emphasis: {
          focus: "adjacency",
          lineStyle: { width: 2 },
        },
      },
    ],
  };
}

function buildTreeOption(
  courseName: string,
  nodes: DisplayNode[],
  stateLabels: Record<string, string>,
) {
  const palette = chartPalette();
  const stateColors = masteryChartColors();
  const fontSize = Math.round(rootFontSize() * 0.75);
  const topics = nodes.filter((node) => !node.core);

  return {
    animation: !prefersReducedMotion(),
    animationDuration: 300,
    tooltip: tooltipConfig(),
    series: [
      {
        type: "tree",
        layout: "orthogonal",
        orient: "LR",
        top: 12,
        bottom: 12,
        left: 84,
        right: 96,
        symbol: "circle",
        symbolSize: 10,
        expandAndCollapse: false,
        initialTreeDepth: -1,
        data: [
          {
            name: courseName,
            core: true,
            itemStyle: {
              color: palette.primary,
              borderColor: palette.primary,
            },
            label: { fontWeight: 600 },
            children: topics.map((node) => ({
              name: node.displayName,
              stateLabel: stateLabels[node.id],
              itemStyle: {
                color:
                  node.state === "untouched"
                    ? palette.card
                    : stateColors[node.state],
                borderColor: stateColors[node.state],
                borderWidth: node.state === "untouched" ? 1 : 0,
              },
            })),
          },
        ],
        lineStyle: {
          color: palette.borderStrong,
          width: 1,
          curveness: 0.5,
        },
        label: {
          show: true,
          position: "right",
          verticalAlign: "middle",
          align: "left",
          distance: 6,
          color: palette.foreground,
          fontSize,
          formatter: (params: { name?: string }) =>
            truncate(params.name ?? "", 12),
        },
        emphasis: { focus: "descendant" },
      },
    ],
  };
}

export function CourseKnowledgeGraph({
  course,
  titleKey = "spaces.courseDetail.graph.title",
  heightClass = "h-72",
  className,
}: CourseKnowledgeGraphProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<GraphView>("force");
  const [fullscreen, setFullscreen] = useState(false);

  const nodes = useMemo<DisplayNode[]>(
    () =>
      mockKnowledgeNodes(course).map((node) => ({
        ...node,
        displayName: translateNodeName(t, node),
      })),
    [course, t],
  );
  const stateLabels = useMemo(
    () =>
      Object.fromEntries(
        nodes.map((node) => [node.id, t(masteryStateLabelKeys[node.state])]),
      ),
    [nodes, t],
  );
  const option = useMemo(
    () =>
      view === "force"
        ? buildForceOption(course.name, nodes, stateLabels)
        : buildTreeOption(course.name, nodes, stateLabels),
    [view, course.name, nodes, stateLabels],
  );
  const ariaLabel = t("spaces.courseDetail.graph.aria", {
    course: course.name,
  });
  const topics = useMemo(() => nodes.filter((node) => !node.core), [nodes]);
  const stateCounts = useMemo(() => {
    const counts = { mastered: 0, learning: 0, untouched: 0 };
    for (const node of topics) counts[node.state] += 1;
    return counts;
  }, [topics]);

  return (
    <SurfaceCard
      title={t(titleKey)}
      sample
      className={cn("@container", className)}
      action={
        <div className="flex items-center gap-1">
          <div
            role="group"
            aria-label={t("spaces.courseDetail.graph.viewLabel")}
            className="border-border bg-background flex h-8 items-center gap-0.5 rounded-lg border p-0.5"
          >
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-pressed={view === "force"}
              className={cn(
                "h-7 px-2 transition-colors duration-[120ms] ease-out",
                view === "force" && "bg-muted",
              )}
              onClick={() => setView("force")}
            >
              <Network data-icon="inline-start" aria-hidden="true" />
              <span className="max-compact:sr-only">
                {t("spaces.courseDetail.graph.force")}
              </span>
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-pressed={view === "tree"}
              className={cn(
                "h-7 px-2 transition-colors duration-[120ms] ease-out",
                view === "tree" && "bg-muted",
              )}
              onClick={() => setView("tree")}
            >
              <ListTree data-icon="inline-start" aria-hidden="true" />
              <span className="max-compact:sr-only">
                {t("spaces.courseDetail.graph.tree")}
              </span>
            </Button>
          </div>
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
        </div>
      }
    >
      <div className="mt-2 flex min-w-0 flex-col gap-5 @2xl:flex-row @2xl:items-start">
        <div className="w-full min-w-0 @2xl:max-w-[26rem] @2xl:flex-1">
          <div key={view} className={cn("view-switch-enter", heightClass)}>
            <BaseChart
              option={option}
              ariaLabel={ariaLabel}
              className="h-full w-full"
            />
          </div>
        </div>
        <div className="@2xl:border-border-subtle min-w-0 flex-1 @2xl:border-l @2xl:pl-5">
          <p className="text-label text-ink-muted">
            {t("spaces.courseDetail.graph.masterySummary")}
          </p>
          <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <li className="text-label text-ink-muted flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="bg-ink-strong size-2 rounded-full"
              />
              {t("spaces.courseDetail.graph.legendCore")}
            </li>
            {(["mastered", "learning", "untouched"] as const).map((state) => (
              <li
                key={state}
                className="text-label text-ink-muted flex items-center gap-1.5"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-2 rounded-full",
                    masteryDotClassNames[state],
                  )}
                />
                {t(masteryStateLabelKeys[state])}
                <span className="text-ink tabular-nums">
                  {stateCounts[state]}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-label text-ink-muted mt-4">
            {t("spaces.courseDetail.graph.conceptCount", {
              count: topics.length,
            })}
          </p>
          <ul className="divide-border-subtle mt-1 flex flex-col divide-y">
            {topics.map((node) => (
              <li
                key={node.id}
                className="flex min-w-0 items-center justify-between gap-3 py-1.5"
              >
                <span
                  className="text-body-dense text-ink min-w-0 truncate"
                  title={node.displayName}
                >
                  {node.displayName}
                </span>
                <MasteryStateBadge state={node.state} className="shrink-0" />
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
