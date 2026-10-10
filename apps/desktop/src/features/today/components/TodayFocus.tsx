import { Clock3, Pause, Play, Square, Timer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TodayPlanItem } from "@/features/today/api/today";

export function TodayFocus({ task }: { task?: TodayPlanItem }) {
  const { t } = useTranslation();
  const [duration, setDuration] = useState(25);
  const [remaining, setRemaining] = useState(25 * 60);
  const [phase, setPhase] = useState<"ready" | "running" | "paused" | "ended">(
    "ready",
  );
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("25");
  const deadline = useRef(0);
  const [boundTask, setBoundTask] = useState<TodayPlanItem>();
  const activeTask = phase === "ready" ? task : boundTask;

  useEffect(() => {
    if (phase !== "running") return;
    const tick = () => {
      const next = Math.max(
        0,
        Math.ceil((deadline.current - Date.now()) / 1000),
      );
      setRemaining(next);
      if (next === 0) setPhase("ended");
    };
    const interval = window.setInterval(tick, 250);
    return () => window.clearInterval(interval);
  }, [phase]);

  const start = () => {
    const seconds = phase === "ended" ? duration * 60 : remaining;
    if (phase === "ready" || phase === "ended") setBoundTask(task);
    setRemaining(seconds);
    deadline.current = Date.now() + seconds * 1000;
    setPhase("running");
  };
  const draftMinutes = Number(draft);
  const validDuration =
    Number.isInteger(draftMinutes) && draftMinutes >= 5 && draftMinutes <= 180;
  const progress = (duration * 60 - remaining) / (duration * 60);
  const time = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;

  return (
    <section
      aria-labelledby="today-focus-title"
      className="today-panel today-focus w-full p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="today-focus-title"
          className="today-heading flex items-center gap-2"
        >
          <Timer className="size-5" aria-hidden="true" />
          {t("today.workspace.focus.title")}
        </h2>
        <div className="flex items-center gap-2">
          <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          <Button
            variant="outline"
            size="sm"
            disabled={phase === "running" || phase === "paused"}
            onClick={() => {
              setDraft(String(duration));
              setEditing(true);
            }}
          >
            {t("today.workspace.focus.edit")}
          </Button>
        </div>
      </div>
      <div className="today-focus-layout mt-4 flex flex-wrap items-center justify-center gap-4">
        <div className="today-focus-timer size-today-timer relative shrink-0">
          <svg
            viewBox="0 0 160 160"
            className="size-full -rotate-90"
            aria-hidden="true"
          >
            <circle
              cx="80"
              cy="80"
              r="70"
              fill="none"
              stroke="var(--today-border)"
              strokeWidth="9"
            />
            <circle
              cx="80"
              cy="80"
              r="70"
              fill="none"
              stroke="var(--today-focus)"
              strokeWidth="9"
              strokeLinecap="round"
              pathLength="100"
              strokeDasharray={`${progress * 100} 100`}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <p
              role="timer"
              aria-label={t("today.workspace.focus.remaining")}
              className="text-stat font-headline tabular-nums"
            >
              {time}
            </p>
            <p className="text-label text-ink-muted mt-1">
              {t(`today.workspace.focus.${phase}`)}
            </p>
          </div>
        </div>
        <div className="today-focus-controls min-w-0 flex-1 basis-32">
          <p
            className="text-body line-clamp-2 font-semibold break-words"
            title={activeTask?.content}
          >
            {activeTask?.content ?? t("today.workspace.focus.sampleTask")}
          </p>
          <p className="text-label text-ink-muted mt-1">
            {activeTask?.course_name ?? t("today.workspace.focus.sampleCourse")}
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              className="h-8 min-w-0 flex-1 gap-1 px-2 text-xs"
              onClick={
                phase === "running"
                  ? () => {
                      setRemaining(
                        Math.max(
                          0,
                          Math.ceil((deadline.current - Date.now()) / 1000),
                        ),
                      );
                      setPhase("paused");
                    }
                  : start
              }
            >
              {phase === "running" ? (
                <Pause aria-hidden="true" />
              ) : (
                <Play aria-hidden="true" />
              )}
              {t(
                `today.workspace.focus.${phase === "running" ? "pause" : phase === "paused" ? "resume" : "start"}`,
              )}
            </Button>
            <Button
              variant="outline"
              className="h-8 gap-1 px-2 text-xs"
              disabled={phase === "ready" || phase === "ended"}
              onClick={() => {
                setRemaining(0);
                setPhase("ended");
              }}
            >
              <Square aria-hidden="true" />
              {t("today.workspace.focus.end")}
            </Button>
          </div>
        </div>
      </div>
      <p className="text-label text-ink-muted mt-3 flex items-center justify-center gap-1">
        <Clock3 className="size-3.5" aria-hidden="true" />
        {t("today.workspace.focus.switchHint")}
      </p>
      <div className="border-border-subtle text-label text-ink-muted mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <span>
          {t("today.workspace.focus.progress", {
            elapsed: Math.floor((duration * 60 - remaining) / 60),
            duration,
          })}
        </span>
      </div>
      <p className="text-label text-ink-muted mt-2">
        {t("today.workspace.focus.demoHint")}
      </p>
      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("today.workspace.focus.edit")}</DialogTitle>
            <DialogDescription>
              {t("today.workspace.focus.durationHint")}
            </DialogDescription>
          </DialogHeader>
          <Label htmlFor="today-focus-duration">
            {t("today.workspace.focus.duration")}
          </Label>
          <Input
            id="today-focus-duration"
            type="number"
            min={5}
            max={180}
            step={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-invalid={!validDuration}
          />
          <DialogFooter>
            <Button
              disabled={!validDuration}
              onClick={() => {
                setDuration(draftMinutes);
                setRemaining(draftMinutes * 60);
                setPhase("ready");
                setEditing(false);
              }}
            >
              {t("today.workspace.focus.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
