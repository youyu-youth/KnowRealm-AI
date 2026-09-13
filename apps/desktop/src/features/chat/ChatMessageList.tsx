import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, RotateCcw, Search } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { ChatMessage } from "@/features/chat/api/types";
import { ChatMarkdown } from "@/features/chat/ChatMarkdown";
import type { ChatToolActivity } from "@/features/chat/useChatStream";

type ChatMessageListProps = {
  messages: ChatMessage[];
  streamingText: string | null;
  toolActivities: ChatToolActivity[];
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

const toolActivityCardClass =
  "bg-surface-subtle text-label flex max-w-full items-center gap-2 rounded-sm px-2.5 py-1.5";
const toolActivityIconClass = "size-3.5 shrink-0";

/** 检索过程卡：加载 / 命中 / 失败三态，图标与文字同时表达状态（不只靠颜色）。 */
function ToolActivityCard({ activity }: { activity: ChatToolActivity }) {
  const { t } = useTranslation();
  if (activity.result === null) {
    return (
      <li className={toolActivityCardClass}>
        <Spinner
          aria-hidden="true"
          className={`${toolActivityIconClass} text-muted-foreground`}
        />
        <span className="text-muted-foreground">
          {t("chat.tools.activity.running", { query: activity.query })}
        </span>
      </li>
    );
  }
  if (activity.result.ok) {
    return (
      <li className={toolActivityCardClass}>
        <Search
          aria-hidden="true"
          className={`${toolActivityIconClass} text-muted-foreground`}
        />
        <span className="text-muted-foreground">
          {t("chat.tools.activity.hits", {
            query: activity.query,
            count: activity.result.hits,
          })}
        </span>
      </li>
    );
  }
  return (
    <li className={toolActivityCardClass}>
      <CircleAlert
        aria-hidden="true"
        className={`${toolActivityIconClass} text-destructive`}
      />
      <span className="text-destructive">
        {t("chat.tools.activity.failed", { query: activity.query })}
      </span>
    </li>
  );
}

export function ChatMessageList({
  messages,
  streamingText,
  toolActivities,
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
  }, [visible.length, streamingText, toolActivities.length]);

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
              {toolActivities.length > 0 ? (
                <ul
                  aria-label={t("chat.tools.activity.label")}
                  className="flex flex-col items-start gap-1.5"
                >
                  {toolActivities.map((activity, index) => (
                    <ToolActivityCard key={index} activity={activity} />
                  ))}
                </ul>
              ) : null}
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
