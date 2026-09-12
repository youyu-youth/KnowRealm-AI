import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { cn } from "@/lib/utils";

type SurfaceCardProps = {
  title: ReactNode;
  /** 标题右侧操作区（链接 / 按钮 / 视图切换等）。 */
  action?: ReactNode;
  /** 是否展示「示意」标记（假数据区域统一明示）。 */
  sample?: boolean;
  /** 标题下方的补充说明，默认不渲染。 */
  description?: ReactNode;
  className?: string;
  contentClassName?: string;
  children?: ReactNode;
};

/** 课堂详情统一卡片壳：白底细边框圆角 + 标题行（操作区/示意标记）。 */
export function SurfaceCard({
  title,
  action,
  sample = false,
  description,
  className,
  contentClassName,
  children,
}: SurfaceCardProps) {
  const { t } = useTranslation();
  return (
    <section
      className={cn(
        "border-border bg-surface-raised flex min-w-0 flex-col rounded-xl border p-4",
        className,
      )}
    >
      <header className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-section font-section text-ink-strong min-w-0 truncate">
            {title}
          </h2>
          {sample ? (
            <StatusTag className="shrink-0">
              {t("spaces.insights.sample")}
            </StatusTag>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </header>
      {description ? (
        <p className="text-label text-ink-muted mt-1">{description}</p>
      ) : null}
      {children ? (
        <div className={cn("min-w-0", contentClassName)}>{children}</div>
      ) : null}
    </section>
  );
}
