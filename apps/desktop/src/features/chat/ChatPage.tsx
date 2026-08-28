import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import { ChatSessionList } from "@/features/chat/ChatSessionList";
import { NewChatButton } from "@/features/chat/NewChatButton";

export function ChatPage() {
  const { t } = useTranslation();
  const sessions = useQuery({
    queryKey: chatKeys.list(),
    queryFn: () => chatApi.list(),
  });

  if (sessions.isPending) {
    return (
      <section className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("chat.title")}
        </h1>
        <p
          role="status"
          className="text-body text-muted-foreground mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("chat.loading")}
        </p>
      </section>
    );
  }

  if (sessions.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("chat.title")}
        </h1>
        <h2 className="text-section font-section text-ink mt-6">
          {t("chat.errorTitle")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {sessions.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void sessions.refetch()}
        >
          {t("chat.retry")}
        </Button>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-w-0 py-8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-headline font-headline text-ink-strong">
            {t("chat.title")}
          </h1>
          <p className="max-w-reading text-body text-muted-foreground mt-2">
            {t("chat.description")}
          </p>
        </div>
        <NewChatButton />
      </div>
      {sessions.data.length === 0 ? (
        <Empty className="border-border mt-8 items-start rounded-none border-t p-0 pt-8 text-start">
          <EmptyHeader className="items-start text-start">
            <EmptyMedia className="justify-start">
              <Bot
                aria-hidden="true"
                className="text-muted-foreground size-8"
              />
            </EmptyMedia>
            <h2 className="text-section font-section text-ink">
              {t("chat.emptyTitle")}
            </h2>
            <EmptyDescription className="max-w-reading text-body text-start">
              {t("chat.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
          <div className="w-full items-start">
            <NewChatButton labelKey="chat.emptyAction" variant="outline" />
          </div>
        </Empty>
      ) : (
        <ChatSessionList sessions={sessions.data} />
      )}
    </section>
  );
}
