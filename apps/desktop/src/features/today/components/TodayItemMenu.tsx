import { ContextMenu } from "@base-ui/react/context-menu";
import { MoreHorizontal, type LucideIcon } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type Action = {
  label: string;
  icon: LucideIcon;
  run: () => void;
  disabled?: boolean;
};

export function TodayItemMenu({
  children,
  actions,
  title,
  quickAction = true,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  actions: [Action, ...Action[]];
  title: string;
  quickAction?: boolean;
}) {
  const { t } = useTranslation();
  const PrimaryIcon = actions[0].icon;
  const items = actions.map(({ label, icon: Icon, run, disabled }) => (
    <DropdownMenuItem key={label} onClick={run} disabled={disabled}>
      <Icon aria-hidden="true" />
      {label}
    </DropdownMenuItem>
  ));
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger render={<div />} {...props}>
        {children}
        <div className="today-row-actions flex items-center gap-1">
          {quickAction ? (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("today.workspace.quickAction", {
                action: actions[0].label,
                title,
              })}
              title={t("today.workspace.quickAction", {
                action: actions[0].label,
                title,
              })}
              disabled={actions[0].disabled}
              onClick={actions[0].run}
            >
              <PrimaryIcon aria-hidden="true" />
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="ghost" size="icon-sm" />}
              aria-label={t("today.workspace.itemActions", { title })}
              className="today-row-menu hover:bg-today-soft focus-visible:ring-2"
            >
              <MoreHorizontal aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {items}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </ContextMenu.Trigger>
      <DropdownMenuContent className="w-56">{items}</DropdownMenuContent>
    </ContextMenu.Root>
  );
}
