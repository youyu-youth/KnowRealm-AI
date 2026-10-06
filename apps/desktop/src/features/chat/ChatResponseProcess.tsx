import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Clock,
  Wrench,
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
import { cn } from "@/lib/utils";

const TOOL_COPY: Record<string, string> = {
  web_search: "chat.tools.activity.webSearch",
  search_library: "chat.tools.activity.library",
  search_courses: "chat.tools.activity.courseSearch",
  search_transcript: "chat.tools.activity",
};

export function ChatResponseProcess({ process }: { process: Process }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(Date.now);
  const running = process.status === "RUNNING";
  const entries = process.entries ?? [];
  const tools = entries.filter((entry) => entry.kind === "tool");
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
      t("chat.process.tool", { tool: entry.tool }),
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
        <p role="status" className="truncate px-2 py-1">
          {entryLabel(latest)}
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
            <li key={entry.id} className="flex min-w-0 items-start gap-2 py-1">
              {entry.kind === "tool" ? (
                entry.status === "RUNNING" ? (
                  <Spinner
                    aria-hidden="true"
                    className="mt-0.5 size-3.5 shrink-0 motion-reduce:animate-none"
                  />
                ) : entry.status === "FAILED" ? (
                  <CircleAlert
                    aria-hidden="true"
                    className="text-destructive mt-0.5 size-3.5 shrink-0"
                  />
                ) : entry.status === "SUCCEEDED" ? (
                  <CircleCheck
                    aria-hidden="true"
                    className="mt-0.5 size-3.5 shrink-0"
                  />
                ) : (
                  <Wrench
                    aria-hidden="true"
                    className="mt-0.5 size-3.5 shrink-0"
                  />
                )
              ) : null}
              <Collapsible className="min-w-0 flex-1">
                <CollapsibleTrigger className="hover:text-ink focus-visible:ring-ring flex w-full min-w-0 cursor-pointer items-center gap-1 rounded-sm text-left focus-visible:ring-2">
                  <span
                    className={cn(
                      "truncate",
                      entry.kind === "tool" &&
                        entry.status === "FAILED" &&
                        "text-destructive",
                    )}
                  >
                    {entryLabel(entry)}
                  </span>
                  <ChevronDown aria-hidden="true" className="size-3 shrink-0" />
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-1 break-words whitespace-pre-wrap">
                  {entryLabel(entry)}
                </CollapsibleContent>
              </Collapsible>
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
