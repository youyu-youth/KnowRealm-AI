import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { MoreHorizontal, Pencil, Star, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChatMessage } from "@/features/chat/api/types";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import { ChatScopeChips } from "@/features/chat/ChatScopeChips";
import {
  DeleteChatDialog,
  RenameChatDialog,
} from "@/features/chat/ChatSessionDialogs";
import { ChatSuggestions } from "@/features/chat/ChatSuggestions";
import { formatChatTimestamp } from "@/features/chat/chatTime";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { useChatStream } from "@/features/chat/useChatStream";
import { cn } from "@/lib/utils";

type ChatConversationViewProps = {
  sessionId: string;
  title: string;
  hasCustomTitle: boolean;
  updatedAt: string;
  recordId: string | null;
  recordDeleted: boolean;
  messages: UseQueryResult<ChatMessage[]>;
  initialPrompt?: string;
};

/** 中栏对话区：标题栏 + 范围 chips + 建议卡 + 消息流 + 输入区。 */
export function ChatConversationView({
  sessionId,
  title,
  hasCustomTitle,
  updatedAt,
  recordId,
  recordDeleted,
  messages,
  initialPrompt,
}: ChatConversationViewProps) {
  const { t, i18n } = useTranslation();
  const { isStreaming, streamedText, streamError, send, stop } =
    useChatStream(sessionId);
  const [composerValue, setComposerValue] = useState(initialPrompt ?? "");
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const favoriteSessionIds = useChatUiStore(
    (state) => state.favoriteSessionIds,
  );
  const toggleFavorite = useChatUiStore((state) => state.toggleFavorite);

  const visibleCount = (messages.data ?? []).filter(
    (message) => message.role !== "SYSTEM",
  ).length;
  const showSuggestions =
    !messages.isPending &&
    !messages.isError &&
    visibleCount === 0 &&
    streamedText === null &&
    !isStreaming &&
    !recordDeleted;
  const favorited = favoriteSessionIds.has(sessionId);

  return (
    <article
      aria-label={t("chat.detailLabel", { title })}
      className="flex h-full min-h-0 flex-col"
    >
      <header className="flex shrink-0 items-start gap-3 px-6 pt-6">
        <div className="min-w-0 flex-1">
          <h1
            className="text-headline font-headline text-ink-strong break-words"
            title={title}
          >
            {title}
          </h1>
          <p className="text-label text-muted-foreground mt-1 flex items-center gap-1.5">
            {recordDeleted ? (
              <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                {t("chat.recordDeleted")}
              </span>
            ) : null}
            {formatChatTimestamp(t, i18n.language, updatedAt)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-0.5 pt-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-pressed={favorited}
            aria-label={
              favorited ? t("chat.menu.unfavorite") : t("chat.menu.favorite")
            }
            onClick={() => toggleFavorite(sessionId)}
          >
            <Star
              aria-hidden="true"
              className={cn(favorited && "fill-chat-accent text-chat-accent")}
            />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("chat.menu.action", { title })}
                />
              }
            >
              <MoreHorizontal aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem onClick={() => setRenameOpen(true)}>
                <Pencil aria-hidden="true" />
                {t("chat.menu.rename")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 aria-hidden="true" />
                {t("chat.menu.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="shrink-0 px-6 pt-4">
        <ChatScopeChips recordId={recordId} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-6">
        {showSuggestions ? <ChatSuggestions onPick={setComposerValue} /> : null}
        {messages.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex flex-1 items-start gap-2 pt-6"
          >
            <Spinner aria-hidden="true" />
            {t("chat.loading")}
          </p>
        ) : messages.isError ? (
          <div className="flex-1 pt-6">
            <Alert variant="destructive">
              <AlertDescription>{messages.error.message}</AlertDescription>
            </Alert>
          </div>
        ) : (
          <ChatMessageList
            messages={messages.data}
            streamingText={streamedText}
            isStreaming={isStreaming}
            streamError={streamError}
            onRetry={send}
            showEmptyHint={!showSuggestions}
          />
        )}
        <ChatComposer
          value={composerValue}
          disabled={messages.isPending || recordDeleted}
          disabledHint={
            recordDeleted ? t("chat.composer.recordDeletedHint") : undefined
          }
          isStreaming={isStreaming}
          onValueChange={setComposerValue}
          onSend={send}
          onStop={stop}
        />
      </div>

      <RenameChatDialog
        sessionId={sessionId}
        displayTitle={title}
        hasCustomTitle={hasCustomTitle}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
      <DeleteChatDialog
        sessionId={sessionId}
        title={title}
        wasActive
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </article>
  );
}
