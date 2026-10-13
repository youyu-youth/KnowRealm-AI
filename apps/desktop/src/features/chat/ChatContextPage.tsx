import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { chatApi } from "@/features/chat/api/chatSessions";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { ContextBudgetDetails } from "@/features/chat/ContextBudgetDetails";
import { ContextRequestList } from "@/features/chat/ContextRequestList";
import { ContextCompactionList } from "@/features/chat/ContextCompactionList";
import { ContextSourcesView } from "@/features/chat/ContextSourcesView";
import {
  selectWebSearchEnabled,
  useChatUiStore,
} from "@/features/chat/chatUiStore";
import { useWebSearchAvailability } from "@/features/chat/useWebSearchAvailability";
import { derivePageSnapshot } from "@/features/chat/pageSnapshot";

export function ChatContextPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { view } = useSearch({ from: "/chat-context/$sessionId" });
  const readSource = (source: string) =>
    void navigate({
      to: "/chat-context/$sessionId",
      params: { sessionId },
      search: { view: "sources", source },
    });
  const [page] = useState(derivePageSnapshot);
  const sessions = useQuery({
    queryKey: chatKeys.list(),
    queryFn: chatApi.list,
  });
  const detail = useQuery({
    queryKey: chatKeys.detail(sessionId),
    queryFn: () => chatApi.get(sessionId),
  });
  const draft = useChatUiStore(
    (state) => state.draftsBySession[sessionId] ?? "",
  );
  const available = useWebSearchAvailability();
  const webSearch = useChatUiStore((state) =>
    selectWebSearchEnabled(
      state,
      sessionId,
      detail.data?.scope !== "FREE",
      detail.data?.mode === "RESEARCH",
    ),
  );
  const preview = { content: draft, web_search: available && webSearch, page };
  const context = useQuery({
    queryKey: chatKeys.context(sessionId, preview),
    queryFn: () => contextApi.preview(sessionId, preview),
    enabled: detail.isSuccess,
    staleTime: 0,
    refetchInterval: 2000,
  });
  return (
    <section
      aria-labelledby="chat-context-title"
      className="flex h-full min-h-0 min-w-0 flex-col"
    >
      <header className="border-border-subtle flex shrink-0 flex-wrap items-center justify-between gap-4 border-b px-6 py-5 max-sm:gap-2 max-sm:px-3 max-sm:py-2">
        <div className="min-w-0">
          <h1
            id="chat-context-title"
            className="text-headline font-headline text-ink-strong max-sm:text-section"
          >
            {t("chat.contextView.title")}
          </h1>
          <p className="text-label text-muted-foreground mt-1 break-words max-sm:hidden">
            {detail.data?.title ?? t("chat.untitled")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/settings"
            search={{ section: "ai" }}
            className={buttonVariants({ variant: "ghost" })}
          >
            {t("chat.contextView.configure")}
          </Link>
          <Link
            to="/chat/$sessionId"
            params={{ sessionId }}
            search={{ prompt: undefined }}
            className={buttonVariants({ variant: "outline" })}
          >
            {t("chat.contextView.back")}
          </Link>
        </div>
      </header>
      <div className="shrink-0 px-6 pt-5 pb-4 max-sm:px-3 max-sm:py-2">
        <Field className="max-w-sm">
          <FieldLabel htmlFor="context-session" className="max-sm:sr-only">
            {t("chat.contextView.session")}
          </FieldLabel>
          <Select
            value={sessionId}
            onValueChange={(value) => {
              if (value)
                void navigate({
                  to: "/chat-context/$sessionId",
                  params: { sessionId: value },
                  search: { view },
                });
            }}
            items={(sessions.data ?? []).map((session) => ({
              value: session.id,
              label: session.title ?? t("chat.untitled"),
            }))}
          >
            <SelectTrigger id="context-session" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {(sessions.data ?? []).map((session) => (
                  <SelectItem key={session.id} value={session.id}>
                    {session.title ?? t("chat.untitled")}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
      </div>
      {sessions.isError || detail.isError || context.isError ? (
        <Alert variant="destructive" className="mx-6 mb-4 shrink-0">
          <AlertDescription>
            {(detail.error ?? context.error ?? sessions.error)?.message}
          </AlertDescription>
          <Button
            variant="outline"
            onClick={() => {
              void detail.refetch();
              void context.refetch();
              void sessions.refetch();
            }}
          >
            {t("chat.retry")}
          </Button>
        </Alert>
      ) : null}
      {!detail.isError && (detail.isPending || context.isPending) ? (
        <p
          role="status"
          className="text-body text-muted-foreground mx-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("chat.loading")}
        </p>
      ) : null}
      {context.data ? (
        <Tabs
          value={view ?? "actual"}
          onValueChange={(value) => {
            if (value === "actual" || value === "next" || value === "sources")
              void navigate({
                to: "/chat-context/$sessionId",
                params: { sessionId },
                search: { view: value === "actual" ? undefined : value },
              });
          }}
          className="min-h-0 flex-1 gap-0"
        >
          <TabsList className="mx-6 mb-3 shrink-0 max-sm:mx-3 max-sm:mb-2">
            <TabsTrigger value="actual">
              {t("chat.contextView.actual")}
            </TabsTrigger>
            <TabsTrigger value="next">{t("chat.contextView.next")}</TabsTrigger>
            <TabsTrigger value="sources">
              {t("chat.contextSources.title")}
            </TabsTrigger>
          </TabsList>
          <TabsContent
            value="actual"
            className="min-h-0 overflow-y-auto px-6 pb-6 max-sm:px-3"
            tabIndex={0}
          >
            <p className="text-body text-muted-foreground mb-5">
              {t("chat.contextView.actualHint")}
            </p>
            <ContextRequestList requests={context.data.actual} />
            <ContextCompactionList
              batches={context.data.compactions ?? []}
              showSummary
              onReadSource={readSource}
            />
          </TabsContent>
          <TabsContent
            value="next"
            className="min-h-0 overflow-y-auto px-6 pb-6 max-sm:px-3"
            tabIndex={0}
          >
            <p className="text-body text-muted-foreground mb-5">
              {t("chat.contextView.nextHint")}
            </p>
            {context.data.next_error_code ? (
              <Alert variant="destructive" className="mb-5">
                <AlertDescription>
                  {t(`errors.${context.data.next_error_code}`)}
                </AlertDescription>
              </Alert>
            ) : null}
            {context.data.next_estimate ? (
              <ContextBudgetDetails estimate={context.data.next_estimate} />
            ) : null}
            <ContextCompactionList
              batches={
                context.data.active_summary ? [context.data.active_summary] : []
              }
              showSummary
              onReadSource={readSource}
            />
          </TabsContent>
          <TabsContent
            value="sources"
            className="min-h-0 overflow-y-auto px-6 pb-6 max-sm:px-3"
            tabIndex={0}
          >
            <ContextSourcesView sessionId={sessionId} />
          </TabsContent>
        </Tabs>
      ) : null}
    </section>
  );
}
