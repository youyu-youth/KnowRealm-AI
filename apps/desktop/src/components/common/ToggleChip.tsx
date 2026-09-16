import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

type ToggleChipProps = ComponentProps<"button"> & {
  active: boolean;
};

/** 紧凑筛选切换片：选中 surface-strong、未选中中性 hover 提亮（DESIGN.md 分段控件）。 */
export function ToggleChip({ active, className, ...props }: ToggleChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "text-label h-7 cursor-pointer rounded-sm px-2.5",
        active
          ? "bg-surface-strong text-ink-strong"
          : "text-ink-muted hover:bg-surface-subtle hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
