import { ListTree, Maximize2, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
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

function rootFontSize(): number {
  const value = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(value) && value > 0 ? value : 16;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
              : masteryChartColors[node.state],
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
                color: masteryChartColors[node.state],
                borderColor: masteryChartColors[node.state],
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

  return (
    <SurfaceCard
      title={t(titleKey)}
      sample
      className={className}
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
      <div key={view} className={cn("view-switch-enter mt-2", heightClass)}>
        <BaseChart
          option={option}
          ariaLabel={ariaLabel}
          className="h-full w-full"
        />
      </div>
      <ul className="text-label text-ink-muted mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="bg-ink-strong size-2 rounded-full"
          />
          {t("spaces.courseDetail.graph.legendCore")}
        </li>
        {(["mastered", "learning", "untouched"] as const).map((state) => (
          <li key={state} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn("size-2 rounded-full", masteryDotClassNames[state])}
            />
            {t(masteryStateLabelKeys[state])}
          </li>
        ))}
      </ul>

      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent className="sm:max-w-5xl">
          <DialogHeader>
            <DialogTitle>{t(titleKey)}</DialogTitle>
            <DialogDescription>
              {t("spaces.courseDetail.graph.fullscreenDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="h-[68vh]">
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
