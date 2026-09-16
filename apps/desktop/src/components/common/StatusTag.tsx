import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export type StatusTagProps = ComponentProps<"span"> & {
  tone?: "neutral" | "success" | "warning" | "danger";
};

const tones = {
  neutral: "bg-surface-strong text-ink-neutral",
  success: "bg-success-soft text-success-foreground",
  warning: "bg-warning-soft text-warning-foreground",
  danger: "bg-danger-soft text-destructive",
};

export function StatusTag({
  className,
  tone = "neutral",
  ...props
}: StatusTagProps) {
  return (
    <span
      className={cn(
        "text-label font-label inline-flex h-6 items-center rounded-sm px-2 whitespace-nowrap",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
