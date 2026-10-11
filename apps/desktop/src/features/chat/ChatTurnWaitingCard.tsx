import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { CircleAlert, PauseCircle } from "lucide-react";
import type { ChatTurn } from "@/features/chat/api/types";
import { waitingReasonText } from "@/features/chat/useChatTurns";

/** 不可安全继续的等待类（与后端 ChatTurnWaitingKind.resumable 同口径）。 */
const UNRESUMABLE_KINDS = new Set(["GRAPH_INCOMPATIBLE", "CHECKPOINT_MISSING"]);

type ChatTurnWaitingCardProps = {
  turn: ChatTurn | null;
  onResume: () => void;
  onStop: () => void;
};

/** 等待 / 中断轮次的处理入口（票 02，规格 §15）：原消息位置之后展示等待
 * 原因与继续、停止动作——继续按钮只重验恢复条件重新排队，不批准业务提案、
 * 不构成重新授权；不可安全继续类只提供停止（新问创建新轮次）。 */
export function ChatTurnWaitingCard({
  turn,
  onResume,
  onStop,
}: ChatTurnWaitingCardProps) {
  const { t } = useTranslation();
  if (turn === null) return null;
  const status = turn.status;
  const background = status === "WAITING_JOB";
  if (status !== "WAITING_USER" && status !== "INTERRUPTED" && !background)
    return null;
  const waiting = status === "WAITING_USER" || background;
  const kind = waiting ? turn.waiting_reason?.kind : undefined;
  const resumable =
    !background && (!waiting || !kind || !UNRESUMABLE_KINDS.has(kind));
  const label = waiting
    ? waitingReasonText(t, kind)
    : t("chat.turn.interrupted");
  return (
    <section
      aria-label={t("chat.turn.waiting.sectionLabel")}
      className="border-border/60 bg-surface-subtle/40 flex flex-wrap items-center gap-2 rounded-2xl border border-dashed px-4 py-2.5"
    >
      {waiting ? (
        <PauseCircle
          aria-hidden="true"
          className="text-muted-foreground size-4 shrink-0"
        />
      ) : (
        <CircleAlert
          aria-hidden="true"
          className="text-muted-foreground size-4 shrink-0"
        />
      )}
      <p className="text-body text-muted-foreground min-w-0 flex-1">
        {label}
        <span className="text-label text-muted-foreground/70 ml-2">
          {t("chat.turn.waiting.submittedAt", {
            time: new Date(turn.created_at).toLocaleString(),
          })}
        </span>
      </p>
      {background ? (
        <ul
          aria-label={t("chat.turn.waiting.tasks")}
          className="text-label text-muted-foreground w-full"
        >
          {turn.background_tasks?.map((task) => (
            <li key={`${task.target_type}-${task.target_id}`}>
              {t(`chat.turn.waiting.taskType.${task.target_type}`)} ·{" "}
              {t(`chat.turn.waiting.taskStatus.${task.status}`, {
                defaultValue: task.status,
              })}
            </li>
          ))}
        </ul>
      ) : null}
      {resumable ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onResume}
          aria-label={t("chat.turn.resume")}
        >
          {t("chat.turn.resume")}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onStop}
        disabled={turn.cancel_requested}
        aria-label={t("chat.turn.stopTurn")}
      >
        {t(turn.cancel_requested ? "chat.turn.stopping" : "chat.turn.stopTurn")}
      </Button>
    </section>
  );
}
