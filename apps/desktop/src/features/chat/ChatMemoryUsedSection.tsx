import { Brain } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useChatUiStore } from "@/features/chat/chatUiStore";

type ChatMemoryUsedSectionProps = {
  sessionId: string;
};

/** 右栏「本轮 AI 记忆」分区（工单 06）：本轮实际注入的记忆条目（边框卡片、
 * 无填充色）；零注入或本轮未发送消息时不展示或展示空态，事实源为 chatUiStore
 * 的当轮临时态。 */
export function ChatMemoryUsedSection({
  sessionId,
}: ChatMemoryUsedSectionProps) {
  const { t } = useTranslation();
  const turnMemory = useChatUiStore((state) => state.turnMemory);
  if (turnMemory === null || turnMemory.sessionId !== sessionId) {
    return null;
  }
  const used = turnMemory.memoryUsed;

  return (
    <section aria-label={t("chat.memory.panelTitle")} className="px-5 pt-6">
      <h2 className="text-section font-section text-ink-strong">
        {t("chat.memory.panelTitle")}
      </h2>
      {used.length > 0 ? (
        <ul
          aria-label={t("chat.memory.panelTitle")}
          className="mt-3 flex flex-col gap-2"
        >
          {used.map((memory) => (
            <li
              key={memory}
              className="border-border-subtle flex items-start gap-2 rounded-lg border px-3 py-2"
            >
              <Brain
                className="text-chat-accent mt-0.5 size-3.5 shrink-0"
                aria-hidden="true"
              />
              <span className="text-label text-ink min-w-0 break-words">
                {memory}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-label text-muted-foreground mt-3">
          {t("chat.memory.usedEmpty")}
        </p>
      )}
    </section>
  );
}
