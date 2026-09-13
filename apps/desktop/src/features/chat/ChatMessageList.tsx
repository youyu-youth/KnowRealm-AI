import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ChatMessage } from "@/features/chat/api/types";
import { ChatMarkdown } from "@/features/chat/ChatMarkdown";

type ChatMessageListProps = {
  messages: ChatMessage[];
  streamingText: string | null;
  isStreaming: boolean;
  streamError: string | null;
  onRetry: (content: string) => void;
  /** 建议卡已承担空会话引导时置 false，避免重复文案。 */
  showEmptyHint?: boolean;
};

const messageTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
});

export function ChatMessageList({
  messages,
  streamingText,
  isStreaming,
  streamError,
  onRetry,
  showEmptyHint = true,
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
        showEmptyHint ? (
          <p className="text-body text-muted-foreground py-8 text-center">
            {t("chat.emptyConversation")}
          </p>
        ) : null
      ) : (
        <ul className="flex flex-col gap-6 py-6">
          {visible.map((message) =>
            message.role === "USER" ? (
              <li key={message.id} className="flex flex-col items-end gap-1">
                <p className="bg-primary text-primary-foreground text-body max-w-[85%] rounded-2xl rounded-ee-md px-4 py-2.5 break-words whitespace-pre-wrap">
                  {message.content}
                </p>
                <time
                  dateTime={message.created_at}
                  className="text-label text-muted-foreground px-1"
                >
                  {messageTimeFormatter.format(new Date(message.created_at))}
                </time>
              </li>
            ) : (
              <li key={message.id} className="flex min-w-0 flex-col gap-3">
                <ChatMarkdown
                  content={message.content}
                  citations={message.citations ?? []}
                />
              </li>
            ),
          )}
          {streamingText !== null ? (
            <li className="flex min-w-0 flex-col gap-3">
              {streamingText ? (
                <ChatMarkdown
                  content={streamingText}
                  citations={[]}
                  streaming
                />
              ) : (
                <p
                  role="status"
                  className="text-body text-muted-foreground animate-pulse"
                >
                  {t("chat.streamingStatus")}
                </p>
              )}
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
        <div className="border-border-subtle mt-4 flex flex-col gap-2 border-t pt-4">
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
