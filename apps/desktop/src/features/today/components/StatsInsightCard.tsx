import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

type StatsInsightCardProps = {
  title: string;
  children: ReactNode;
};

// 洞察小图卡（DESIGN.md §5 统计图表卡）：全站唯一允许的卡片面板分区；
// 示意标签明示假数据，待真数据域接入后摘除。
export function StatsInsightCard({ title, children }: StatsInsightCardProps) {
  const { t } = useTranslation();

  return (
    <section
      aria-label={title}
      className="bg-card border-border/60 flex min-w-0 flex-col gap-3 rounded-lg border p-5"
    >
      <div className="flex items-center gap-2">
        <h3 className="text-section font-section text-ink min-w-0 truncate">
          {title}
        </h3>
        <span className="bg-surface-subtle text-muted-foreground text-label shrink-0 rounded-xs px-1.5 py-0.5">
          {t("today.stats.insights.sampleTag")}
        </span>
      </div>
      {children}
    </section>
  );
}
