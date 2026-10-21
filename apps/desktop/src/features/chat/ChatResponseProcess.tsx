import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  CircleAlert,
  CircleCheck,
  CircleEllipsis,
  CircleSlash,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Spinner } from "@/components/ui/spinner";
import type {
  ChatProcessEntry,
  ChatResponseProcess as Process,
} from "@/features/chat/api/types";
import {
  COMMENTARY_ICON,
  TOOL_ICON_FALLBACK,
  TOOL_ICONS,
} from "@/features/chat/toolIcons";
import { cn } from "@/lib/utils";

const TOOL_COPY: Record<string, string> = {
  web_search: "chat.tools.activity.webSearch",
  search_library: "chat.tools.activity.library",
  search_courses: "chat.tools.activity.courseSearch",
  search_transcript: "chat.tools.activity",
  search_context: "chat.contextSources.finding",
  read_context: "chat.contextSources.reading",
};

type ToolEntry = Extract<ChatProcessEntry, { kind: "tool" }>;

function isToolEntry(entry: ChatProcessEntry): entry is ToolEntry {
  return entry.kind === "tool";
}

/** 完全相同的公开说明只保留第一条：同文重复对读者无区分意义。 */
function dedupeCommentary(entries: ChatProcessEntry[]): ChatProcessEntry[] {
  const seen = new Set<string>();
  return entries.filter((entry) => {
    if (entry.kind !== "commentary") return true;
    if (seen.has(entry.text)) return false;
    seen.add(entry.text);
    return true;
  });
}

function statusIcon(status: ToolEntry["status"]) {
  switch (status) {
    case "RUNNING":
      return (
        <Spinner
          aria-hidden="true"
          className="mt-0.5 size-3 shrink-0 motion-reduce:animate-none"
        />
      );
    case "SUCCEEDED":
      return (
        <CircleCheck aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
      );
    case "FAILED":
      return (
        <CircleAlert
          aria-hidden="true"
          className="text-destructive mt-0.5 size-3 shrink-0"
        />
      );
    case "INTERRUPTED":
      return (
        <CircleSlash aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
      );
    case "AWAITING_CONFIRMATION":
      return (
        <CircleEllipsis aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
      );
  }
}

function EntryIcon({
  entry,
  className,
}: {
  entry: ChatProcessEntry;
  className?: string;
}) {
  const Icon =
    entry.kind === "tool"
      ? (TOOL_ICONS[entry.tool] ?? TOOL_ICON_FALLBACK)
      : COMMENTARY_ICON;
  return <Icon aria-hidden="true" className={className} />;
}

/**
 * 单条过程：默认单行截断，点击整行原地换成换行全文——
 * 同一句文案任何状态下只显示一份（行内不再嵌套可展开副本）。
 */
function ProcessEntryRow({
  entry,
  label,
}: {
  entry: ChatProcessEntry;
  label: string;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const failed = entry.kind === "tool" && entry.status === "FAILED";
  return (
    <li className="flex min-w-0 items-start gap-2 py-1">
      <EntryIcon
        entry={entry}
        className={cn("mt-0.5 size-3.5 shrink-0", failed && "text-destructive")}
      />
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        title={
          entry.kind === "tool"
            ? t(`chat.process.toolStatus.${entry.status}`)
            : undefined
        }
        className="hover:text-ink focus-visible:ring-ring flex min-w-0 flex-1 cursor-pointer items-start gap-1 rounded-sm text-left focus-visible:ring-2"
      >
        <span
          className={cn(
            "min-w-0 flex-1",
            expanded ? "break-words whitespace-pre-wrap" : "truncate",
            failed && "text-destructive",
          )}
        >
          {label}
        </span>
        {entry.kind === "tool" ? statusIcon(entry.status) : null}
        <ChevronDown
          aria-hidden="true"
          className={cn("mt-0.5 size-3 shrink-0", expanded && "rotate-180")}
        />
      </button>
    </li>
  );
}

export function ChatResponseProcess({ process }: { process: Process }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(Date.now);
  const running = process.status === "RUNNING";
  const entries = dedupeCommentary(process.entries ?? []);
  const tools = entries.filter(isToolEntry);
  const latest = tools[tools.length - 1];
  const failures = tools.filter((entry) => entry.status === "FAILED").length;

  useEffect(() => {
    if (!running) return;
    const tick = () => {
      if (!document.hidden) setNow(Date.now());
    };
    const timer = window.setInterval(tick, 1000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [running]);

  if (
    !running &&
    process.status === "COMPLETED" &&
    entries.length === 0 &&
    process.history_saved !== false
  )
    return null;

  const seconds = Math.floor(
    Math.max(
      process.elapsed_ms ?? 0,
      running ? now - Date.parse(process.started_at) : 0,
    ) / 1000,
  );
  const duration =
    seconds < 60
      ? t("chat.process.seconds", { count: seconds })
      : t("chat.process.minutes", {
          minutes: Math.floor(seconds / 60),
          seconds: seconds % 60,
        });
  const stage = running
    ? t(
        tools.some((entry) => entry.status === "RUNNING")
          ? "chat.process.executing"
          : "chat.process.generating",
      )
    : t(`chat.process.status.${process.status}`);

  function entryLabel(entry: ChatProcessEntry): string {
    if (entry.kind === "commentary") return entry.text;
    if (entry.kind === "delegation")
      return t("chat.delegation.progress", {
        status: t(`chat.delegation.status.${entry.status}`),
        id: entry.execution_id,
        attempt: entry.execution_attempt,
      });
    const copy = TOOL_COPY[entry.tool];
    if (copy && ["RUNNING", "SUCCEEDED", "FAILED"].includes(entry.status)) {
      return t(
        `${copy}.${entry.status === "RUNNING" ? "running" : entry.status === "FAILED" ? "failed" : "hits"}`,
        {
          query: entry.query,
          count: entry.hits ?? 0,
        },
      );
    }
    return [
      t("chat.process.tool", {
        tool: t(`chat.process.toolNames.${entry.tool}`, {
          defaultValue: entry.tool,
        }),
      }),
      entry.query,
      t(`chat.process.toolStatus.${entry.status}`),
    ]
      .filter(Boolean)
      .join(" · ");
  }

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="text-label text-ink-muted min-w-0"
    >
      <CollapsibleTrigger
        render={<Button variant="ghost" size="sm" />}
        className="max-w-full cursor-pointer gap-2"
      >
        {running ? (
          <Spinner aria-hidden="true" className="motion-reduce:animate-none" />
        ) : process.status === "COMPLETED" ? (
          <Clock aria-hidden="true" />
        ) : (
          <CircleAlert aria-hidden="true" />
        )}
        <span className="truncate">
          {stage} · {t("chat.process.duration", { duration })} ·{" "}
          {t("chat.process.calls", { count: tools.length })}
          {failures > 0
            ? ` · ${t("chat.process.failures", { count: failures })}`
            : ""}
        </span>
        <ChevronDown
          data-icon="inline-end"
          aria-hidden="true"
          className={cn("shrink-0", open && "rotate-180")}
        />
      </CollapsibleTrigger>
      {running && latest && !open ? (
        <p role="status" className="flex min-w-0 items-center gap-2 px-2 py-1">
          <EntryIcon entry={latest} className="size-3.5 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{entryLabel(latest)}</span>
        </p>
      ) : null}
      {process.history_saved === false ? (
        <p role="status" className="text-destructive px-2 py-1">
          {t("chat.process.historyIncomplete")}
        </p>
      ) : null}
      <CollapsibleContent>
        <ol
          aria-label={t("chat.process.details")}
          tabIndex={entries.length > 10 ? 0 : undefined}
          className={cn(
            "flex flex-col gap-1 px-2 py-2",
            entries.length > 10 &&
              "max-h-80 overflow-y-auto overscroll-contain",
          )}
        >
          {entries.map((entry) => (
            <ProcessEntryRow
              key={entry.id}
              entry={entry}
              label={entryLabel(entry)}
            />
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
