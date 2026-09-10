import { Tooltip } from "@base-ui/react/tooltip";
import type { ReactElement } from "react";

type AppTooltipProps = {
  label: string;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
};

export function AppTooltip({
  label,
  children,
  side = "right",
}: AppTooltipProps) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger render={children} delay={400} />
      <Tooltip.Portal>
        <Tooltip.Positioner side={side} sideOffset={6} className="z-50">
          <Tooltip.Popup className="bg-surface-overlay text-label text-ink-strong border-border-subtle rounded-sm border px-2 py-1.5">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
