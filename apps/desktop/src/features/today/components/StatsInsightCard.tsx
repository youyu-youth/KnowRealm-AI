import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { StatusTag } from "@/components/common/StatusTag";

type StatsInsightCardProps = {
  title: string;
  children: ReactNode;
  className?: string;
};

// 洞察小图卡（DESIGN.md §5 统计图表卡）：全站唯一允许的卡片面板分区；
// 示意标签明示假数据，待真数据域接入后摘除。
export function StatsInsightCard({
  title,
  children,
  className,
}: StatsInsightCardProps) {
  const { t } = useTranslation();

  return (
    <section
      aria-label={title}
      className={cn(
        "bg-surface-raised border-border-subtle flex min-w-0 flex-col gap-3 rounded-md border p-4",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <h3 className="text-section font-section text-ink min-w-0 truncate">
          {title}
        </h3>
        <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
      </div>
      {children}
    </section>
  );
}
