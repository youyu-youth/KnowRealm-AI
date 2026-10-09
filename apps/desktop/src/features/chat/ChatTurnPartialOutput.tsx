import { useTranslation } from "react-i18next";
import { ChatMarkdown } from "@/features/chat/ChatMarkdown";
import type { ChatMessageTurn } from "@/features/chat/api/types";

type ChatTurnPartialOutputProps = {
  turn: ChatMessageTurn | null | undefined;
};

/** 终态轮次的部分输出（规格 §5/§15）：取消 / 失败 / 中断且无最终消息时，按
 * 轮次引用展示已持久化正文与原因——不把「无最终消息」等同于需要补答。 */
export function ChatTurnPartialOutput({ turn }: ChatTurnPartialOutputProps) {
  const { t } = useTranslation();
  if (turn == null || turn.output_text === "") return null;
  const label =
    turn.status === "CANCELLED"
      ? t("chat.turn.partial.cancelled")
      : turn.status === "FAILED"
        ? t("chat.turn.partial.failed")
        : t("chat.turn.partial.interrupted");
  return (
    <section
      aria-label={label}
      className="border-border/60 bg-surface-subtle/40 flex flex-col gap-1.5 rounded-2xl rounded-ss-md border border-dashed px-4 py-2.5"
    >
      <p className="text-label text-muted-foreground">{label}</p>
      <ChatMarkdown content={turn.output_text} citations={[]} />
    </section>
  );
}
