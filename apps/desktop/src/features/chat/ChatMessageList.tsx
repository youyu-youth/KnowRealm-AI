import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ChatCitation, ChatMessage } from "@/features/chat/api/types";
import { cn } from "@/lib/utils";

type ChatMessageListProps = {
  messages: ChatMessage[];
  streamingText: string | null;
  isStreaming: boolean;
  streamError: string | null;
  onRetry: (content: string) => void;
};

const CITATION_SPLIT_RE = /(\[\d{1,3}\])/;
const CITATION_MARKER_RE = /^\[(\d{1,3})\]$/;

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
              {message.role === "ASSISTANT" &&
              (message.citations?.length ?? 0) > 0 ? (
                <CitationBubble message={message} />
              ) : (
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
              )}
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

const markerButtonClass =
  "text-primary hover:text-primary-hover focus-visible:ring-ring/40 mx-0.5 align-super text-label rounded-sm font-medium focus-visible:ring-3";

/** 带引用的回答气泡：正文 [n] 角标与引用区都可点击，跳转该记录转写页定位原文。 */
function CitationBubble({ message }: { message: ChatMessage }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const citations = message.citations ?? [];
  const citationMap = new Map<number, ChatCitation>(
    citations.map((citation) => [citation.index, citation]),
  );

  function openCitation(citation: ChatCitation) {
    void navigate({
      to: "/records/$recordId",
      params: { recordId: citation.record_id },
      search: { tab: "transcript", highlight: citation.quote },
    });
  }

  return (
    <>
      <p className="text-body bg-surface-subtle text-ink border-border rounded-card border px-4 py-2.5 break-words whitespace-pre-wrap">
        {message.content.split(CITATION_SPLIT_RE).map((part, index) => {
          const marker = CITATION_MARKER_RE.exec(part);
          if (marker === null) return <span key={index}>{part}</span>;
          const citation = citationMap.get(Number(marker[1]));
          if (citation === undefined) return <span key={index}>{part}</span>;
          return (
            <button
              key={index}
              type="button"
              className={markerButtonClass}
              aria-label={t("chat.citation.jump", { index: citation.index })}
              onClick={() => openCitation(citation)}
            >
              {part}
            </button>
          );
        })}
      </p>
      <ul
        aria-label={t("chat.citation.listLabel")}
        className="border-border bg-surface-subtle rounded-card mt-1 flex max-w-full flex-col gap-1 rounded-ss-none border p-3"
      >
        {citations.map((citation) => (
          <li key={citation.index}>
            <button
              type="button"
              className="text-label text-muted-foreground hover:text-ink focus-visible:ring-ring/40 w-full rounded-sm text-start focus-visible:ring-3"
              onClick={() => openCitation(citation)}
            >
              <span className="text-primary font-medium">
                [{citation.index}]
              </span>{" "}
              {citation.quote}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
