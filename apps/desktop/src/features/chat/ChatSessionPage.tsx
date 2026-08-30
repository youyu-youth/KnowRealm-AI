import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Link, useParams, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { ProviderSetupGuide } from "@/components/common/ProviderSetupGuide";
import type { ChatMessage } from "@/features/chat/api/types";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import { ChatSessionList } from "@/features/chat/ChatSessionList";
import { NewChatButton } from "@/features/chat/NewChatButton";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { useChatStream } from "@/features/chat/useChatStream";
import { ApiError } from "@/services/http/client";

export function ChatSessionPage() {
  const { t } = useTranslation();
  const { sessionId } = useParams({ from: "/chat/$sessionId" });
  const { prompt } = useSearch({ from: "/chat/$sessionId" });
  const detail = useQuery({
    queryKey: chatKeys.detail(sessionId),
    queryFn: () => chatApi.get(sessionId),
  });
  const sessions = useQuery({
    queryKey: chatKeys.list(),
    queryFn: () => chatApi.list(),
  });
  const messages = useQuery({
    queryKey: chatKeys.messages(sessionId),
    queryFn: () => chatApi.getMessages(sessionId),
  });
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: () => settingsApi.getLlmProvider(),
  });
  const { isStreaming, streamedText, streamError, send, stop } =
    useChatStream(sessionId);
  const providerReady =
    provider.data?.provider != null && provider.data.provider.has_api_key;

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex h-full min-w-0 py-8">
      <aside
        aria-label={t("chat.listLabel")}
        className="border-border hidden w-72 shrink-0 flex-col gap-3 border-r pr-4 md:flex"
      >
        <NewChatButton labelKey="chat.newSession" variant="outline" />
        {sessions.isPending ? (
          <p
            role="status"
            className="text-label text-muted-foreground flex items-center gap-2"
          >
            <Spinner aria-hidden="true" className="size-3" />
            {t("chat.loading")}
          </p>
        ) : sessions.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{sessions.error.message}</AlertDescription>
          </Alert>
        ) : sessions.data.length === 0 ? (
          <p className="text-label text-muted-foreground">
            {t("chat.emptyTitle")}
          </p>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ChatSessionList
              sessions={sessions.data}
              activeSessionId={sessionId}
            />
          </div>
        )}
      </aside>

      <div className="min-h-0 min-w-0 flex-1 pl-6">
        {detail.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("chat.loading")}
          </p>
        ) : detail.isError ? (
          detail.error instanceof ApiError && detail.error.status === 404 ? (
            <Empty className="border-border items-start rounded-none border-t p-0 pt-8 text-start">
              <EmptyHeader className="items-start text-start">
                <h2 className="text-section font-section text-ink">
                  {t("chat.notFoundTitle")}
                </h2>
                <EmptyDescription className="max-w-reading text-body text-start">
                  {t("chat.notFoundDescription")}
                </EmptyDescription>
              </EmptyHeader>
              <Link
                to="/chat"
                className="text-body text-primary hover:text-primary-hover focus-visible:ring-ring/40 rounded-sm focus-visible:ring-3"
              >
                {t("chat.backToList")}
              </Link>
            </Empty>
          ) : (
            <div role="alert">
              <h2 className="text-section font-section text-ink">
                {t("chat.errorTitle")}
              </h2>
              <p className="max-w-reading text-body text-muted-foreground mt-2">
                {detail.error.message}
              </p>
              <Button
                variant="outline"
                className="mt-5"
                onClick={() => void detail.refetch()}
              >
                {t("chat.retry")}
              </Button>
            </div>
          )
        ) : (
          <article
            aria-label={t("chat.detailLabel", {
              title: detail.data.title ?? t("chat.untitled"),
            })}
            className="flex h-full min-h-0 flex-col"
          >
            <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2">
              <h1
                className="text-headline font-headline text-ink-strong break-words"
                title={detail.data.title ?? t("chat.untitled")}
              >
                {detail.data.title ?? t("chat.untitled")}
              </h1>
              {detail.data.record_deleted ? (
                <span className="text-label bg-destructive/10 text-destructive font-label rounded-xs px-2 py-0.5">
                  {t("chat.recordDeleted")}
                </span>
              ) : null}
            </header>
            <div className="mt-6 flex min-h-0 flex-1 flex-col">
              {provider.isPending ? null : (
                <ChatConversation
                  key={sessionId}
                  initialComposerValue={prompt}
                  providerReady={providerReady}
                  recordDeleted={detail.data.record_deleted}
                  messages={messages}
                  stream={{
                    isStreaming,
                    streamedText,
                    streamError,
                    send,
                    stop,
                  }}
                />
              )}
            </div>
          </article>
        )}
      </div>
      <span className="sr-only" aria-live="polite">
        {isStreaming ? t("chat.streamingStatus") : ""}
      </span>
    </section>
  );
}

type ChatConversationProps = {
  initialComposerValue?: string;
  providerReady: boolean;
  recordDeleted: boolean;
  messages: UseQueryResult<ChatMessage[], Error>;
  stream: ReturnType<typeof useChatStream>;
};

/** 会话内容区：未配置供应商时显示跳设置页的引导卡，否则显示消息历史 + 输入区。 */
function ChatConversation({
  initialComposerValue,
  providerReady,
  recordDeleted,
  messages,
  stream,
}: ChatConversationProps) {
  const { t } = useTranslation();
  const { isStreaming, streamedText, streamError, send, stop } = stream;
  if (!providerReady) {
    return (
      <div className="flex min-h-0 flex-1 items-start overflow-y-auto pt-8">
        <ProviderSetupGuide />
      </div>
    );
  }
  return (
    <>
      {messages.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("chat.loading")}
        </p>
      ) : messages.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{messages.error.message}</AlertDescription>
        </Alert>
      ) : (
        <ChatMessageList
          messages={messages.data}
          streamingText={streamedText}
          isStreaming={isStreaming}
          streamError={streamError}
          onRetry={send}
        />
      )}
      <ChatComposer
        disabled={messages.isPending || recordDeleted}
        disabledHint={
          recordDeleted ? t("chat.composer.recordDeletedHint") : undefined
        }
        isStreaming={isStreaming}
        initialValue={initialComposerValue}
        onSend={send}
        onStop={stop}
      />
    </>
  );
}
