import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { ContextSourcePinActions } from "@/features/chat/ContextSourcePinActions";
import { ContextSourceExcludeAction } from "@/features/chat/ContextSourceExcludeAction";

export function ContextSourceReader({
  sessionId,
  sourceId,
  version,
  cursor,
  quote,
  offset,
  onContinue,
  pinId,
  pinVersion,
}: {
  sessionId: string;
  sourceId: string;
  version?: string;
  cursor?: string;
  quote?: string;
  offset?: number;
  onContinue: (cursor?: string) => void;
  pinId?: string;
  pinVersion?: number;
}) {
  const { t } = useTranslation();
  const body = {
    source_id: sourceId,
    version,
    cursor,
    quote,
    offset,
    max_chars: 2400,
  };
  const read = useQuery({
    queryKey: chatKeys.source(sessionId, body),
    queryFn: () => contextApi.read(sessionId, body),
    staleTime: 0,
    retry: false,
  });
  return (
    <section
      aria-label={t("chat.contextSources.original")}
      className="flex min-w-0 flex-col gap-3"
    >
      <h2 className="text-section">{t("chat.contextSources.original")}</h2>
      {read.isPending ? (
        <p role="status" className="text-body flex items-center gap-2">
          <Spinner aria-hidden="true" />
          {t("chat.loading")}
        </p>
      ) : null}
      {read.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{read.error.message}</AlertDescription>
          <Button variant="outline" onClick={() => void read.refetch()}>
            {t("chat.retry")}
          </Button>
        </Alert>
      ) : null}
      {read.data ? (
        <>
          <ContextSourcePinActions
            key={`${read.data.source.version}:${read.data.offset}:${pinId ?? ""}`}
            sessionId={sessionId}
            original={read.data}
            pinId={pinId}
            pinVersion={pinVersion}
          />
          {read.data.source.kind === "record" ||
          read.data.source.kind === "library" ? (
            <ContextSourceExcludeAction
              sessionId={sessionId}
              sourceId={read.data.source.source_id}
              sourceVersion={read.data.source.version}
            />
          ) : null}
          <p className="text-body break-words">{read.data.source.title}</p>
          <dl className="text-label text-muted-foreground flex flex-col gap-1 break-all">
            <div>
              <dt className="inline">{t("chat.contextSources.identity")}: </dt>
              <dd className="inline">{read.data.source.source_id}</dd>
            </div>
            <div>
              <dt className="inline">{t("chat.contextSources.version")}: </dt>
              <dd className="inline">{read.data.source.version}</dd>
            </div>
            {Object.entries(read.data.source.locator ?? {}).map(
              ([key, value]) =>
                value !== null ? (
                  <div key={key}>
                    <dt className="inline">
                      {t(`chat.contextSources.locator.${key}`, {
                        defaultValue: key,
                      })}
                      :{" "}
                    </dt>
                    <dd className="inline">{value}</dd>
                  </div>
                ) : null,
            )}
          </dl>
          <p className="text-label text-muted-foreground">
            {t("chat.contextSources.fragmentHint")}
          </p>
          <div
            tabIndex={0}
            aria-label={t("chat.contextSources.content")}
            className="bg-surface-subtle text-body focus-visible:ring-ring min-w-0 p-4 break-words whitespace-pre-wrap focus-visible:ring-2 focus-visible:outline-none"
          >
            {read.data.content || t("chat.contextSources.emptyContent")}
          </div>
          <p
            role="status"
            className="text-label text-muted-foreground tabular-nums"
          >
            {t("chat.contextSources.remaining", {
              count: read.data.remaining,
              offset: read.data.offset,
            })}
          </p>
          <div className="flex flex-wrap gap-2">
            {read.data.next_cursor ? (
              <Button
                variant="outline"
                onClick={() => onContinue(read.data?.next_cursor ?? undefined)}
              >
                {t("chat.contextSources.continueRead")}
              </Button>
            ) : null}
            {cursor ? (
              <Button variant="ghost" onClick={() => onContinue()}>
                {t("chat.contextSources.restartRead")}
              </Button>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
