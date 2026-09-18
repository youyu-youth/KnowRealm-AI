import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { prefersReducedMotion, rootFontSize } from "@/charts/dom";
import type { echarts } from "@/charts/echarts";
import { chartPalette, cssVar, darkTooltipStyle } from "@/charts/token";
import type {
  BrainGraph,
  ConceptMastery,
  MasteryStatus,
} from "@/features/courses/api/types";
import {
  masteryDotCssVars,
  masteryStatusLabelKeys,
  masteryStatuses,
} from "@/features/courses/masteryStatus";
import { cn } from "@/lib/utils";

type GraphTooltipParams = {
  data?: {
    name?: string;
    importance?: number;
    occurrenceCount?: number;
    recordCount?: number;
    masteryStatus?: MasteryStatus;
  };
};

type GraphNodeDatum = {
  id: string;
  name: string;
  importance: number;
  occurrenceCount: number;
  recordCount: number;
  masteryStatus?: MasteryStatus;
  symbolSize: number;
  itemStyle: { color: string; borderColor?: string; borderWidth?: number };
};

/** 重要度 1~5 映射到灰阶（5 最深），对齐 DESIGN.md 图表黑白灰明度阶。 */
function importanceGrayRamp(): string[] {
  const palette = chartPalette();
  return [
    palette.faintForeground ?? "#858B96",
    palette.mutedForeground ?? "#666B75",
    palette.neutralForeground ?? "#4B4F58",
    palette.foreground ?? "#2F3239",
    palette.primary ?? "#1A1C20",
  ];
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function buildGraphOption(
  graph: BrainGraph,
  masteryByConceptId: ReadonlyMap<string, ConceptMastery> | undefined,
  t: ReturnType<typeof useTranslation>["t"],
): echarts.EChartsCoreOption {
  const palette = chartPalette();
  const grays = importanceGrayRamp();
  const reducedMotion = prefersReducedMotion();
  const fontSize = Math.round(rootFontSize() * 0.75);
  const maxRecordCount = Math.max(
    ...graph.nodes.map((node) => node.record_count),
    1,
  );

  const nodes: GraphNodeDatum[] = graph.nodes.map((node) => ({
    id: node.id,
    name: node.canonical_name,
    importance: node.importance,
    occurrenceCount: node.occurrence_count,
    recordCount: node.record_count,
    // 非侵入式掌握标记：只挂到标签/tooltip，不改动节点主色（重要度灰阶）。
    masteryStatus: masteryByConceptId?.get(node.id)?.status,
    symbolSize: 14 + Math.round((node.record_count / maxRecordCount) * 20),
    itemStyle: {
      color: grays[Math.min(Math.max(node.importance, 1), 5) - 1],
      borderColor: palette.card,
      borderWidth: 1.5,
    },
  }));
  const links = graph.edges.map((edge) => ({
    source: edge.source_concept_id,
    target: edge.target_concept_id,
    lineStyle: {
      width: edge.evidence_count > 1 ? 1.25 : 0.75,
      opacity: edge.evidence_count > 1 ? 0.52 : 0.3,
      type: edge.stale ? ("dashed" as const) : ("solid" as const),
    },
  }));

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
      formatter: ({ data }: GraphTooltipParams) => {
        if (!data?.name) return "";
        const lines = [
          data.name,
          t("spaces.courseDetail.brain.graph.tooltipImportance", {
            importance: data.importance ?? 0,
          }),
          t("spaces.courseDetail.brain.concepts.occurrences", {
            count: data.occurrenceCount ?? 0,
          }),
          t("spaces.courseDetail.brain.concepts.records", {
            count: data.recordCount ?? 0,
          }),
        ];
        if (data.masteryStatus) {
          lines.push(
            t("spaces.courseDetail.brain.graph.tooltipMastery", {
              status: t(masteryStatusLabelKeys[data.masteryStatus]),
            }),
          );
        }
        return lines.join("\n");
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        scaleLimit: { min: 0.7, max: 3 },
        draggable: true,
        cursor: "pointer",
        labelLayout: { hideOverlap: true },
        label: {
          show: true,
          position: "right",
          distance: 5,
          color: palette.foreground,
          fontSize,
          formatter: ({ data }: { data?: GraphNodeDatum }) => {
            const name = truncate(data?.name ?? "", 12);
            // 状态点 = 辅助标记；文字标签仍是节点主体（状态不止靠颜色，tooltip 有文字）。
            return data?.masteryStatus
              ? `{dot_${data.masteryStatus}|●} ${name}`
              : name;
          },
          rich: Object.fromEntries(
            masteryStatuses.map((status) => [
              `dot_${status}`,
              { color: cssVar(masteryDotCssVars[status]), fontSize },
            ]),
          ),
        },
        data: nodes,
        links,
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

type CourseBrainGraphProps = {
  courseName: string;
  graph: BrainGraph;
  /** 概念 → 掌握快照（查询层组合，缺数据/失败时不传即诚实无标记）。 */
  masteryByConceptId?: ReadonlyMap<string, ConceptMastery>;
  /** 点击概念节点；由父组件打开概念详情面板。 */
  onSelect: (conceptId: string) => void;
  heightClass?: string;
  className?: string;
};

/** Course Brain 正式图谱：节点 = CONFIRMED 概念，边 = CONFIRMED 关系（过期边虚线）。 */
export function CourseBrainGraph({
  courseName,
  graph,
  masteryByConceptId,
  onSelect,
  heightClass = "h-[26rem]",
  className,
}: CourseBrainGraphProps) {
  const { t } = useTranslation();
  const option = useMemo(
    () => buildGraphOption(graph, masteryByConceptId, t),
    [graph, masteryByConceptId, t],
  );
  const handleSelect = useCallback(
    (params: echarts.ECElementEvent) => {
      const data = params.data as { id?: unknown } | undefined;
      if (
        params.dataType === "node" &&
        typeof data?.id === "string" &&
        data.id !== ""
      ) {
        onSelect(data.id);
      }
    },
    [onSelect],
  );

  return (
    <div className={cn(heightClass, className)}>
      <BaseChart
        option={option}
        ariaLabel={t("spaces.courseDetail.brain.graph.aria", {
          course: courseName,
        })}
        onItemSelect={handleSelect}
        className="h-full w-full"
      />
    </div>
  );
}
