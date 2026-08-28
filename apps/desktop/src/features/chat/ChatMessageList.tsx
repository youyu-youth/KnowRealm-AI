import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/features/chat/api/types";
import { cn } from "@/lib/utils";

type ChatMessageListProps = {
  messages: ChatMessage[];
  streamingText: string | null;
  isStreaming: boolean;
  streamError: string | null;
  onRetry: (content: string) => void;
};

export function ChatMessageList({
  messages,
  streamingText,
  isStreaming,
  streamError,
  onRetry,
}: ChatMessageListProps) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  // SYSTEM 是会话创建时的角色快照，仅喂给模型，不渲染给用户。
  const visible = messages.filter((message) => message.role !== "SYSTEM");
  const lastVisible = visible[visible.length - 1];
  const interrupted =
    lastVisible !== undefined &&
    lastVisible.role === "USER" &&
    !isStreaming &&
    streamingText === null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [visible.length, streamingText]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
      {visible.length === 0 && streamingText === null ? (
        <p className="text-body text-muted-foreground py-8 text-center">
          {t("chat.emptyConversation")}
        </p>
      ) : (
        <ul className="flex flex-col gap-4 py-6">
          {visible.map((message) => (
            <li
              key={message.id}
              className={cn(
                "flex w-fit max-w-full flex-col",
                message.role === "USER" ? "self-end" : "self-start",
              )}
            >
              <p
                className={cn(
                  "text-body rounded-card px-4 py-2.5 break-words whitespace-pre-wrap",
                  message.role === "USER"
                    ? "bg-primary text-primary-foreground"
                    : "bg-surface-subtle text-ink border-border border",
                )}
              >
                {message.content}
              </p>
            </li>
          ))}
          {streamingText !== null ? (
            <li className="flex w-fit max-w-full flex-col self-start">
              <p
                role="status"
                className="text-body bg-surface-subtle text-ink border-border rounded-card border px-4 py-2.5 break-words whitespace-pre-wrap"
              >
                {streamingText || t("chat.streamingStatus")}
              </p>
            </li>
          ) : null}
        </ul>
      )}

      {streamError !== null ? (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>{streamError}</AlertDescription>
        </Alert>
      ) : null}

      {interrupted ? (
        <div className="border-border mt-4 flex flex-col gap-2 border-t pt-4">
          <p className="text-label text-muted-foreground">
            {t("chat.interruptedDescription")}
          </p>
          <div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRetry(lastVisible.content)}
            >
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              {t("chat.retryAnswer")}
            </Button>
          </div>
        </div>
      ) : null}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}
