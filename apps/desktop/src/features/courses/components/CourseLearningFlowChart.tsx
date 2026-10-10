import { useAppearanceSnapshot } from "@/hooks/useAppearanceSnapshot";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { BaseChart } from "@/charts/BaseChart";
import { prefersReducedMotion, rootFontSize } from "@/charts/dom";
import { chartPalette, cssVar, darkTooltipStyle } from "@/charts/token";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import {
  LEARNING_CHAIN_DROP_KEYS,
  LEARNING_CHAIN_STAGE_KEYS,
  type LearningChain,
  type LearningChainDropKey,
  type LearningChainNodeKey,
} from "@/features/courses/courseLearningChain";
import { cn } from "@/lib/utils";

type CourseLearningFlowChartProps = {
  courseName: string;
  chain: LearningChain;
  className?: string;
};

type SankeyTooltipParams = {
  dataType?: string;
  name?: string;
  data?: { source?: string; target?: string; value?: number };
};

const NODE_KEYS: LearningChainNodeKey[] = [
  ...LEARNING_CHAIN_STAGE_KEYS,
  ...LEARNING_CHAIN_DROP_KEYS,
];

function nodeCounts(
  chain: LearningChain,
): Record<LearningChainNodeKey, number> {
  return {
    capture: chain.reached.capture,
    transcribe: chain.reached.transcribe,
    summary: chain.reached.summary,
    confirm: chain.reached.confirm,
    notStarted: chain.drops.notStarted,
    transcribing: chain.drops.transcribing,
    summarizing: chain.drops.summarizing,
    pendingConfirm: chain.drops.pendingConfirm,
    failed: chain.drops.failed,
  };
}

/** 单色明度阶：主链 ink、确认与待确认 ink-strong、停留项 faint、失败用语义危险色。 */
function nodeColors(): Record<LearningChainNodeKey, string | undefined> {
  const palette = chartPalette();
  return {
    capture: palette.foreground,
    transcribe: palette.foreground,
    summary: palette.foreground,
    confirm: palette.primary,
    notStarted: palette.faintForeground,
    transcribing: palette.faintForeground,
    summarizing: palette.faintForeground,
    pendingConfirm: palette.primary,
    failed: cssVar("--destructive"),
  };
}

function buildSankeyOption(
  chain: LearningChain,
  labels: Record<LearningChainNodeKey, string>,
) {
  const palette = chartPalette();
  const colors = nodeColors();
  const counts = nodeCounts(chain);
  const fontSize = Math.round(rootFontSize() * 0.75);
  const countByName = Object.fromEntries(
    NODE_KEYS.map((key) => [labels[key], counts[key]]),
  );

  return {
    animation: !prefersReducedMotion(),
    animationDuration: 480,
    animationEasing: "quinticOut" as const,
    tooltip: {
      ...darkTooltipStyle(),
      confine: true,
      formatter: (params: SankeyTooltipParams) => {
        if (params.dataType === "edge") {
          const { source, target, value } = params.data ?? {};
          return source && target ? `${source} → ${target}: ${value}` : "";
        }
        return params.name ?? "";
      },
    },
    series: [
      {
        type: "sankey",
        left: 8,
        right: 96,
        top: 8,
        bottom: 8,
        nodeWidth: 12,
        nodeGap: 16,
        nodeAlign: "justify",
        draggable: false,
        emphasis: { focus: "adjacency" },
        lineStyle: { color: "source", opacity: 0.16, curveness: 0.5 },
        label: {
          show: true,
          position: "right",
          distance: 6,
          fontSize,
          color: palette.foreground,
          formatter: (params: { name?: string }) => {
            const name = params.name ?? "";
            return `${name} ${countByName[name] ?? ""}`.trim();
          },
        },
        data: NODE_KEYS.filter((key) => counts[key] > 0).map((key) => ({
          name: labels[key],
          itemStyle: { color: colors[key], borderWidth: 0 },
          ...(key === "failed"
            ? { label: { color: cssVar("--destructive") } }
            : {}),
        })),
        links: chain.flows.map((flow) => ({
          source: labels[flow.source],
          target: labels[flow.target],
          value: flow.value,
          lineStyle:
            flow.target === "failed"
              ? { color: cssVar("--destructive"), opacity: 0.32 }
              : undefined,
        })),
      },
    ],
  };
}

/** 学习链桑基流图：真实记录状态派生的守恒流转 + 文字摘要（图表可访问性）。 */
export function CourseLearningFlowChart({
  courseName,
  chain,
  className,
}: CourseLearningFlowChartProps) {
  const { t } = useTranslation();
  useAppearanceSnapshot();
  const labels = useMemo(
    () =>
      Object.fromEntries(
        NODE_KEYS.map((key) => [key, t(`spaces.courseDetail.chain.${key}`)]),
      ) as Record<LearningChainNodeKey, string>,
    [t],
  );
  const option = buildSankeyOption(chain, labels);
  const activeDrops = LEARNING_CHAIN_DROP_KEYS.filter(
    (key) => chain.drops[key] > 0,
  );

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.chain.flowTitle")}
      className={cn("@container", className)}
    >
      <div className="mt-2 flex min-w-0 flex-col gap-5 @2xl:flex-row @2xl:items-start">
        <div className="w-full min-w-0 @2xl:max-w-[26rem] @2xl:flex-1">
          <div className="view-switch-enter h-72">
            <BaseChart
              option={option}
              ariaLabel={t("spaces.courseDetail.chain.aria", {
                course: courseName,
              })}
              className="h-full w-full"
            />
          </div>
        </div>
        <div className="@2xl:border-border-subtle min-w-0 flex-1 @2xl:border-l @2xl:pl-5">
          <p className="text-label text-ink-muted">
            {t("spaces.courseDetail.chain.stagesTitle")}
          </p>
          <dl className="divide-border-subtle mt-1 flex flex-col divide-y">
            {LEARNING_CHAIN_STAGE_KEYS.map((key) => (
              <div
                key={key}
                className="flex min-w-0 items-baseline justify-between gap-3 py-1.5"
              >
                <dt className="text-body-dense text-ink truncate">
                  {t(`spaces.courseDetail.chain.${key}`)}
                </dt>
                <dd className="text-label text-ink-muted shrink-0 tabular-nums">
                  {t("spaces.courseDetail.chain.stageValue", {
                    count: chain.reached[key],
                    percent: chain.conversion[key],
                  })}
                </dd>
              </div>
            ))}
          </dl>
          {activeDrops.length > 0 ? (
            <>
              <p className="text-label text-ink-muted mt-4">
                {t("spaces.courseDetail.chain.dropsTitle")}
              </p>
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
                {activeDrops.map((key: LearningChainDropKey) => (
                  <li
                    key={key}
                    className="text-label text-ink-muted flex items-center gap-1.5"
                  >
                    {t(`spaces.courseDetail.chain.${key}`)}
                    <span className="text-ink tabular-nums">
                      {chain.drops[key]}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {chain.drops.failed > 0 ? (
            <p className="text-label text-destructive mt-4">
              {t("spaces.courseDetail.chain.failedNote", {
                count: chain.drops.failed,
              })}
            </p>
          ) : null}
        </div>
      </div>
    </SurfaceCard>
  );
}
