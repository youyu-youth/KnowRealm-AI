import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { ContextSourceReader } from "@/features/chat/ContextSourceReader";

export function ContextSourcesView({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const search = useSearch({ from: "/chat-context/$sessionId" });
  const [query, setQuery] = useState(search.q ?? "");
  const body = { query: search.q ?? "", cursor: search.searchCursor, limit: 8 };
  const sources = useQuery({
    queryKey: chatKeys.sources(sessionId, body),
    queryFn: () => contextApi.search(sessionId, body),
    staleTime: 0,
    retry: false,
  });
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <p className="text-body text-muted-foreground">
        {t("chat.contextSources.scopeHint")}
      </p>
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void navigate({
            to: "/chat-context/$sessionId",
            params: { sessionId },
            search: { view: "sources", q: query || undefined },
          });
        }}
      >
        <Field className="min-w-0 flex-1">
          <FieldLabel htmlFor="context-source-query">
            {t("chat.contextSources.searchLabel")}
          </FieldLabel>
          <Input
            id="context-source-query"
            value={query}
            maxLength={200}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("chat.contextSources.searchPlaceholder")}
          />
        </Field>
        <Button type="submit">{t("chat.contextSources.search")}</Button>
      </form>
      {sources.isPending ? (
        <p role="status" className="text-body flex items-center gap-2">
          <Spinner aria-hidden="true" />
          {t("chat.loading")}
        </p>
      ) : null}
      {sources.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{sources.error.message}</AlertDescription>
          <Button variant="outline" onClick={() => void sources.refetch()}>
            {t("chat.retry")}
          </Button>
        </Alert>
      ) : null}
      {sources.data ? (
        <section
          aria-label={t("chat.contextSources.results")}
          className="flex flex-col gap-3"
        >
          {sources.data.sources.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>{t("chat.contextSources.noResults")}</EmptyTitle>
                <EmptyDescription>
                  {t("chat.contextSources.noResultsHint")}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="flex flex-col gap-2">
              {sources.data.sources.map((source) => (
                <li key={source.source_id} className="min-w-0">
                  <Button
                    variant="ghost"
                    className="h-auto w-full justify-start py-2 whitespace-normal"
                    onClick={() =>
                      void navigate({
                        to: "/chat-context/$sessionId",
                        params: { sessionId },
                        search: {
                          ...search,
                          source: source.source_id,
                          version: source.version,
                          cursor: undefined,
                          offset:
                            typeof source.locator?.start_offset === "number"
                              ? source.locator.start_offset
                              : undefined,
                          quote:
                            typeof source.locator?.quote === "string"
                              ? source.locator.quote
                              : undefined,
                        },
                      })
                    }
                  >
                    <span className="min-w-0 text-left break-words">
                      <span className="text-label text-muted-foreground block">
                        {t(`chat.contextSources.kinds.${source.kind}`)}
                      </span>
                      {source.title || source.source_id}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            {sources.data.next_cursor ? (
              <Button
                variant="outline"
                onClick={() =>
                  void navigate({
                    to: "/chat-context/$sessionId",
                    params: { sessionId },
                    search: {
                      ...search,
                      searchCursor: sources.data?.next_cursor ?? undefined,
                    },
                  })
                }
              >
                {t("chat.contextSources.continueSearch", {
                  count: sources.data.remaining,
                })}
              </Button>
            ) : null}
            {search.searchCursor ? (
              <Button
                variant="ghost"
                onClick={() =>
                  void navigate({
                    to: "/chat-context/$sessionId",
                    params: { sessionId },
                    search: { ...search, searchCursor: undefined },
                  })
                }
              >
                {t("chat.contextSources.restartSearch")}
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}
      {search.source ? (
        <ContextSourceReader
          sessionId={sessionId}
          sourceId={search.source}
          pinId={search.pin}
          pinVersion={search.pinVersion}
          version={search.version}
          cursor={search.cursor}
          quote={search.quote}
          offset={search.offset}
          onContinue={(cursor) =>
            void navigate({
              to: "/chat-context/$sessionId",
              params: { sessionId },
              search: {
                ...search,
                cursor,
                quote: cursor ? search.quote : undefined,
                offset: cursor ? search.offset : undefined,
              },
            })
          }
        />
      ) : null}
    </div>
  );
}
