import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
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
import { chatApi } from "@/features/chat/api/chatSessions";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { ContextBudgetDetails } from "@/features/chat/ContextBudgetDetails";
import { ContextRequestList } from "@/features/chat/ContextRequestList";
import {
  selectWebSearchEnabled,
  useChatUiStore,
} from "@/features/chat/chatUiStore";
import { useWebSearchAvailability } from "@/features/chat/useWebSearchAvailability";
import { derivePageSnapshot } from "@/features/chat/pageSnapshot";

export function ChatContextPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
  const context = useQuery({
    queryKey: chatKeys.context(sessionId),
    queryFn: () =>
      contextApi.preview(sessionId, {
        content: draft,
        web_search: available && webSearch,
        page: derivePageSnapshot(),
      }),
    enabled: detail.isSuccess,
    staleTime: 0,
    refetchInterval: 2000,
  });
  return (
    <section
      aria-labelledby="chat-context-title"
      className="flex h-full min-h-0 min-w-0 flex-col"
    >
      <header className="border-border-subtle flex shrink-0 flex-wrap items-center justify-between gap-4 border-b px-6 py-5">
        <div className="min-w-0">
          <h1
            id="chat-context-title"
            className="text-headline font-headline text-ink-strong"
          >
            {t("chat.contextView.title")}
          </h1>
          <p className="text-label text-muted-foreground mt-1 break-words">
            {detail.data?.title ?? t("chat.untitled")}
          </p>
        </div>
        <Link
          to="/chat/$sessionId"
          params={{ sessionId }}
          search={{ prompt: undefined }}
          className={buttonVariants({ variant: "outline" })}
        >
          {t("chat.contextView.back")}
        </Link>
      </header>
      <div
        className="min-h-0 flex-1 overflow-y-auto px-6 py-6"
        tabIndex={0}
        aria-label={t("chat.contextView.title")}
      >
        <Field className="max-w-sm">
          <FieldLabel htmlFor="context-session">
            {t("chat.contextView.session")}
          </FieldLabel>
          <Select
            value={sessionId}
            onValueChange={(value) => {
              if (value)
                void navigate({
                  to: "/chat-context/$sessionId",
                  params: { sessionId: value },
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
        {sessions.isError || detail.isError || context.isError ? (
          <Alert variant="destructive" className="mt-6">
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
            className="text-body text-muted-foreground mt-6 flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("chat.loading")}
          </p>
        ) : null}
        {context.data ? (
          <div className="mt-8 grid min-w-0 grid-cols-1 gap-8 xl:grid-cols-2">
            <section aria-labelledby="context-actual-title" className="min-w-0">
              <h2
                id="context-actual-title"
                className="text-section font-section text-ink"
              >
                {t("chat.contextView.actual")}
              </h2>
              <p className="text-body text-muted-foreground mt-2 mb-5">
                {t("chat.contextView.actualHint")}
              </p>
              <ContextRequestList requests={context.data.actual} />
            </section>
            <section aria-labelledby="context-next-title" className="min-w-0">
              <h2
                id="context-next-title"
                className="text-section font-section text-ink"
              >
                {t("chat.contextView.next")}
              </h2>
              <p className="text-body text-muted-foreground mt-2 mb-5">
                {t("chat.contextView.nextHint")}
              </p>
              {context.data.next_estimate ? (
                <ContextBudgetDetails estimate={context.data.next_estimate} />
              ) : null}
              {context.data.next_error_code ? (
                <Alert variant="destructive" className="mt-5">
                  <AlertDescription>
                    {t(`errors.${context.data.next_error_code}`)}
                  </AlertDescription>
                </Alert>
              ) : null}
              <Link
                to="/settings"
                search={{ section: "ai" }}
                className={buttonVariants({
                  variant: "outline",
                  className: "mt-5",
                })}
              >
                {t("chat.contextView.configure")}
              </Link>
            </section>
          </div>
        ) : null}
      </div>
    </section>
  );
}
