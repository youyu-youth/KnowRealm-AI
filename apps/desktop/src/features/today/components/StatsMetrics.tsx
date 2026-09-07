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
import { cn } from "@/lib/utils";

type TodayStats = components["schemas"]["TodayStatsOut"];

type StatCell = {
  icon: LucideIcon;
  labelKey: string;
  parts: DurationPart[];
  // 分隔线只画在水平相邻格之间。默认 3 列折行（行首格不带左线），
  // wide 6 列时仅第 1 格不带；折行处不留悬空分隔线。
  borderClass: string;
};

const bordered = "border-border border-l pl-6";
const rowStartAt3Cols = "border-border border-l-0 wide:border-l wide:pl-6";

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
      borderClass: "",
    },
    {
      icon: FileStack,
      labelKey: "today.stats.metrics.recordCount",
      parts: countParts(stats.record_count),
      borderClass: bordered,
    },
    {
      icon: BookOpenText,
      labelKey: "today.stats.metrics.courseCount",
      parts: countParts(stats.course_count),
      borderClass: bordered,
    },
    {
      icon: Sparkles,
      labelKey: "today.stats.metrics.aiSummaryCount",
      parts: countParts(stats.ai_summary_count),
      borderClass: rowStartAt3Cols,
    },
    {
      icon: ListChecks,
      labelKey: "today.stats.metrics.quiz",
      parts: [
        { text: String(stats.quiz_answered_count), muted: false },
        { text: "/", muted: true },
        { text: String(stats.quiz_generated_count), muted: false },
      ],
      borderClass: bordered,
    },
    {
      icon: MessagesSquare,
      labelKey: "today.stats.metrics.chatTurnCount",
      parts: countParts(stats.chat_turn_count),
      borderClass: bordered,
    },
  ];

  return (
    <div className="wide:grid-cols-6 grid grid-cols-3 gap-y-6">
      {cells.map((cell) => (
        <div
          key={cell.labelKey}
          className={cn(
            "flex min-w-0 items-center gap-3 py-2",
            cell.borderClass,
          )}
        >
          <span
            aria-hidden="true"
            className="text-ink flex size-8 shrink-0 items-center justify-center"
          >
            <cell.icon className="size-6 stroke-[1.6]" />
          </span>
          <div className="min-w-0">
            <p className="text-label text-muted-foreground truncate">
              {t(cell.labelKey)}
            </p>
            <p className="text-ink-strong mt-0.5 text-xl font-semibold tabular-nums">
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
