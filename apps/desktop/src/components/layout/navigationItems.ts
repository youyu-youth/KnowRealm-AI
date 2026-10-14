import {
  Archive,
  Bot,
  CalendarDays,
  Inbox,
  Library,
  UserRound,
} from "lucide-react";

export const navigationItems = [
  { labelKey: "nav.today", icon: CalendarDays, to: "/" },
  { labelKey: "nav.inbox", icon: Inbox, to: "/inbox" },
  { labelKey: "nav.spaces", icon: Archive, to: "/spaces" },
  { labelKey: "nav.chat", icon: Bot, to: "/chat" },
  { labelKey: "nav.library", icon: Library, to: "/library" },
  { labelKey: "nav.profile", icon: UserRound },
] as const;

export const activeNavClass =
  "flex h-9 items-center gap-3 overflow-hidden rounded-md bg-surface-subtle px-3 text-body font-semibold text-ink-strong transition-colors focus-visible:ring-3 focus-visible:ring-ring/40";
export const inactiveNavClass =
  "flex h-9 items-center gap-3 overflow-hidden rounded-md px-3 text-body font-medium text-muted-foreground transition-colors hover:bg-surface-subtle hover:text-ink-strong focus-visible:ring-3 focus-visible:ring-ring/40";
