import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Construction } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from "@/components/ui/empty";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import { ChatSessionList } from "@/features/chat/ChatSessionList";
import { NewChatButton } from "@/features/chat/NewChatButton";
import { ApiError } from "@/services/http/client";

export function ChatSessionPage() {
  const { t } = useTranslation();
  const { sessionId } = useParams({ from: "/chat/$sessionId" });
  const detail = useQuery({
    queryKey: chatKeys.detail(sessionId),
    queryFn: () => chatApi.get(sessionId),
  });
  const sessions = useQuery({
    queryKey: chatKeys.list(),
    queryFn: () => chatApi.list(),
  });

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

      <div className="min-w-0 flex-1 pl-6">
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
          >
            <header>
              <h1
                className="text-headline font-headline text-ink-strong break-words"
                title={detail.data.title ?? t("chat.untitled")}
              >
                {detail.data.title ?? t("chat.untitled")}
              </h1>
            </header>
            <Empty className="border-border mt-8 items-start rounded-none border-t p-0 pt-8 text-start">
              <EmptyHeader className="items-start text-start">
                <EmptyMedia className="justify-start">
                  <Construction
                    aria-hidden="true"
                    className="text-muted-foreground size-8"
                  />
                </EmptyMedia>
                <h2 className="text-section font-section text-ink">
                  {t("chat.messagesUnavailableTitle")}
                </h2>
                <EmptyDescription className="max-w-reading text-body text-start">
                  {t("chat.messagesUnavailableDescription")}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </article>
        )}
      </div>
    </section>
  );
}
