import { Pause, Play, Settings2, Shuffle, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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

export function TodayFocus({
  task,
  onDropTask,
  onNextTask,
}: {
  task?: TodayPlanItem;
  onDropTask?: (id: string) => void;
  onNextTask?: () => void;
}) {
  const { t } = useTranslation();
  const [dragOver, setDragOver] = useState(false);
  const [duration, setDuration] = useState(25);
  const [remaining, setRemaining] = useState(25 * 60);
  const [phase, setPhase] = useState<"ready" | "running" | "paused" | "ended">(
    "ready",
  );
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("25");
  const [goals, setGoals] = useState([true, true, false, false]);
  const deadline = useRef(0);
  const [boundTask, setBoundTask] = useState<TodayPlanItem>();
  const activeTask =
    phase === "running" || phase === "paused" ? boundTask : task;

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
      data-drag-over={dragOver}
      onDragOver={(event) => {
        if (
          !onDropTask ||
          !event.dataTransfer.types.includes(
            "application/x-knowrealm-plan-item",
          )
        )
          return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDragOver(true);
      }}
      onDragLeave={(event) => {
        if (
          !event.currentTarget.contains(
            event.relatedTarget instanceof Node ? event.relatedTarget : null,
          )
        )
          setDragOver(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        const id = event.dataTransfer.getData(
          "application/x-knowrealm-plan-item",
        );
        if (id) onDropTask?.(id);
      }}
    >
      <div className="today-focus-copy">
        <div className="flex flex-wrap items-center gap-2">
          <h2
            id="today-focus-title"
            tabIndex={-1}
            className="text-label font-semibold"
          >
            {t("today.workspace.focus.title")}
          </h2>
          <span className="text-label today-focus-meta">
            {activeTask?.course_name ?? t("today.redesign.sampleCourse")}
          </span>
          {!activeTask && (
            <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          )}
        </div>
        <p className="today-focus-task" title={activeTask?.content}>
          {activeTask?.content ?? t("today.redesign.sampleTask")}
        </p>
        <p className="today-focus-description">
          {activeTask?.goal_title ?? t("today.redesign.sampleDescription")}
        </p>
        <div className="today-focus-goals">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-body font-semibold">
              {t("today.redesign.learningGoal")}
            </p>
            {activeTask ? (
              <span className="text-label">
                {activeTask.estimated_minutes == null
                  ? t("today.progress.unestimated")
                  : t("today.planTodos.minutes", {
                      minutes: activeTask.estimated_minutes,
                    })}
              </span>
            ) : (
              <>
                <span className="text-body font-semibold tabular-nums">
                  {goals.filter(Boolean).length} / {goals.length}
                </span>
                <progress
                  className="today-goal-progress"
                  value={goals.filter(Boolean).length}
                  max={goals.length}
                  aria-label={t("today.redesign.goalProgress")}
                />
                <span className="text-label tabular-nums">
                  {Math.round(
                    (goals.filter(Boolean).length / goals.length) * 100,
                  )}
                  %
                </span>
              </>
            )}
          </div>
          {activeTask ? (
            <p className="text-label mt-3 break-words">
              {activeTask.goal_title} · {activeTask.scheduled_date}
            </p>
          ) : (
            <div className="today-goal-list">
              {goals.map((checked, index) => (
                <label key={index} className="flex items-start gap-2">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(value) =>
                      setGoals((previous) =>
                        previous.map((goal, i) =>
                          i === index ? value === true : goal,
                        ),
                      )
                    }
                  />
                  <span>{t(`today.redesign.sampleGoals.${index}`)}</span>
                </label>
              ))}
            </div>
          )}
        </div>
        {task &&
          boundTask?.item_id !== task.item_id &&
          (phase === "running" || phase === "paused") && (
            <p role="status" className="text-label mt-3">
              {t("today.workspace.nextFocus", { title: task.content })}
            </p>
          )}
        <p className="text-label today-focus-meta mt-3">
          {t("today.workspace.focus.demoHint")}
        </p>
      </div>
      <div className="today-focus-clock-column">
        <div className="today-focus-timer">
          <svg
            viewBox="0 0 200 200"
            className="today-clock-ticks"
            aria-hidden="true"
          >
            <circle
              cx="100"
              cy="100"
              r="94"
              fill="none"
              stroke="var(--today-surface)"
              strokeWidth="7"
            />
            {Array.from({ length: 30 }, (_, index) => (
              <line
                key={index}
                x1="100"
                y1="17"
                x2="100"
                y2={index % 5 === 0 ? "28" : "24"}
                transform={`rotate(${index * 12} 100 100)`}
                stroke="currentColor"
                strokeWidth={index % 5 === 0 ? "1.5" : "1"}
              />
            ))}
            <circle
              cx="100"
              cy="100"
              r="94"
              fill="none"
              stroke="var(--today-focus-muted)"
              strokeWidth="3"
              pathLength="100"
              strokeDasharray={`${progress * 100} 100`}
              transform="rotate(-90 100 100)"
            />
          </svg>
          <div className="today-clock-content">
            <p
              role="timer"
              aria-label={t("today.workspace.focus.remaining")}
              className="today-clock-time"
            >
              {time}
            </p>
            <p className="text-label mt-1">
              {t(`today.workspace.focus.${phase}`)}
            </p>
            <Button
              className="today-clock-start mt-3"
              size="sm"
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
          </div>
        </div>
        <div className="today-focus-buttons">
          <Button
            variant="outline"
            size="sm"
            disabled={phase === "running" || phase === "paused" || !onNextTask}
            onClick={onNextTask}
          >
            <Shuffle aria-hidden="true" />
            {t("today.redesign.nextTask")}
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label={t("today.workspace.focus.edit")}
            disabled={phase === "running" || phase === "paused"}
            onClick={() => {
              setDraft(String(duration));
              setEditing(true);
            }}
          >
            <Settings2 aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="sm"
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
        <p className="text-label today-focus-meta mt-2 text-center">
          {t("today.workspace.focus.progress", {
            elapsed: Math.floor((duration * 60 - remaining) / 60),
            duration,
          })}
        </p>
        {onDropTask && (
          <p className="text-label today-focus-meta mt-1 text-center">
            {t("today.workspace.dropFocus")}
          </p>
        )}
      </div>
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
