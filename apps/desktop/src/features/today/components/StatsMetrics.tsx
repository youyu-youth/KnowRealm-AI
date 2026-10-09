import type { components } from "@knowrealm/api-types";
import {
  BookOpenText,
  FileStack,
  ListChecks,
  MessagesSquare,
  Sparkles,
  Timer,
  type LucideIcon,
} from "lucide-react";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import {
  formatLearningDurationParts,
  type DurationPart,
} from "@/features/today/duration";

type TodayStats = components["schemas"]["TodayStatsOut"];

type StatCell = {
  icon: LucideIcon;
  labelKey: string;
  parts: DurationPart[];
};

function countParts(value: number): DurationPart[] {
  return [{ text: String(value), muted: false }];
}

type StatsMetricsProps = {
  stats: TodayStats;
};

export function StatsMetrics({ stats }: StatsMetricsProps) {
  const { t } = useTranslation();

  const cells: StatCell[] = [
    {
      icon: Timer,
      labelKey: "today.stats.metrics.learningDuration",
      parts: formatLearningDurationParts(stats.total_learning_ms, t),
    },
    {
      icon: FileStack,
      labelKey: "today.stats.metrics.recordCount",
      parts: countParts(stats.record_count),
    },
    {
      icon: BookOpenText,
      labelKey: "today.stats.metrics.courseCount",
      parts: countParts(stats.course_count),
    },
    {
      icon: Sparkles,
      labelKey: "today.stats.metrics.aiSummaryCount",
      parts: countParts(stats.ai_summary_count),
    },
    {
      icon: ListChecks,
      labelKey: "today.stats.metrics.quiz",
      parts: [
        { text: String(stats.quiz_answered_count), muted: false },
        { text: "/", muted: true },
        { text: String(stats.quiz_generated_count), muted: false },
      ],
    },
    {
      icon: MessagesSquare,
      labelKey: "today.stats.metrics.chatTurnCount",
      parts: countParts(stats.chat_turn_count),
    },
  ];

  return (
    <div className="today-metrics grid grid-cols-2 gap-3 pt-3">
      {cells.map((cell) => (
        <div
          key={cell.labelKey}
          className="flex min-w-0 items-start gap-2 py-2"
        >
          <span
            aria-hidden="true"
            className="text-ink flex size-8 shrink-0 items-center justify-center"
          >
            <cell.icon className="size-6 stroke-[1.6]" />
          </span>
          <div className="min-w-0">
            <p className="text-label text-muted-foreground break-words">
              {t(cell.labelKey)}
            </p>
            <p className="text-ink-strong text-body mt-0.5 font-semibold tabular-nums">
              {cell.parts.map((part, partIndex) => (
                <Fragment key={partIndex}>
                  {partIndex > 0 ? " " : null}
                  {part.muted ? (
                    <span className="text-label font-label text-muted-foreground">
                      {part.text}
                    </span>
                  ) : (
                    part.text
                  )}
                </Fragment>
              ))}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
