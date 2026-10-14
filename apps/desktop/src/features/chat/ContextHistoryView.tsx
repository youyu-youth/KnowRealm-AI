import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { useContextRuleChange } from "@/features/chat/useContextRuleChange";

export function ContextHistoryView({
  sessionId,
  version,
  segment,
}: {
  sessionId: string;
  version: number;
  segment: number;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const search = useSearch({ from: "/chat-context/$sessionId" });
  const offset = search.historyOffset ?? 0;
  const change = useContextRuleChange(sessionId);
  const history = useQuery({
    queryKey: chatKeys.contextHistory(sessionId, offset, version),
    queryFn: () => contextApi.history(sessionId, offset, version),
    staleTime: 0,
  });
  const page = (next: number) =>
    void navigate({
      to: "/chat-context/$sessionId",
      params: { sessionId },
      search: { ...search, historyOffset: next || undefined },
    });
  return (
    <section
      aria-label={t("chat.contextRules.history")}
      className="flex min-w-0 flex-col gap-3 pb-16"
    >
      <h3 className="text-section">{t("chat.contextRules.history")}</h3>
      {history.isPending ? <p role="status">{t("chat.loading")}</p> : null}
      {history.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{history.error.message}</AlertDescription>
          <Button
            variant="outline"
            onClick={() => {
              page(0);
              void history.refetch();
            }}
          >
            {t("chat.retry")}
          </Button>
        </Alert>
      ) : null}
      {history.data?.turns.length === 0 ? (
        <p className="text-body text-muted-foreground">
          {t("chat.contextRules.emptyHistory")}
        </p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {history.data?.turns.map((turn) => (
          <li
            key={turn.turn_id}
            className="border-border-subtle flex min-w-0 flex-col gap-2 border-b pb-3"
          >
            <p className="text-body break-words">{turn.title}</p>
            <p className="text-label text-muted-foreground break-all">
              {t("chat.contextRules.turnState", {
                segment: turn.segment,
                state: t(
                  turn.excluded
                    ? "chat.contextRules.excluded"
                    : turn.included
                      ? "chat.contextRules.included"
                      : "chat.contextRules.old",
                ),
              })}{" "}
              · {turn.turn_id}
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="ghost"
                disabled={change.isPending}
                onClick={() =>
                  change.mutate({
                    action: turn.excluded ? "RESTORE_TURN" : "EXCLUDE_TURN",
                    turn_ids: [turn.turn_id],
                    expected_version: version,
                  })
                }
              >
                {t(
                  turn.excluded
                    ? "chat.contextRules.restoreTurn"
                    : "chat.contextRules.excludeTurn",
                )}
              </Button>
              {turn.segment < segment &&
              !turn.included &&
              turn.status === "COMPLETED" ? (
                <Button
                  variant="outline"
                  disabled={change.isPending || turn.excluded}
                  onClick={() =>
                    change.mutate({
                      action: "INCLUDE_HISTORY",
                      turn_ids: [turn.turn_id],
                      expected_version: version,
                    })
                  }
                >
                  {t("chat.contextRules.includeTurn")}
                </Button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        {offset > 0 ? (
          <Button
            variant="ghost"
            onClick={() => page(Math.max(0, offset - 20))}
          >
            {t("chat.contextRules.previous")}
          </Button>
        ) : null}
        {history.data?.next_offset != null ? (
          <Button
            variant="outline"
            onClick={() => page(history.data?.next_offset ?? 0)}
          >
            {t("chat.contextRules.next")}
          </Button>
        ) : null}
      </div>
      {change.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{change.error.message}</AlertDescription>
        </Alert>
      ) : null}
      {change.isSuccess ? (
        <p role="status" className="text-label text-muted-foreground">
          {t("chat.contextRules.saved", {
            version: change.data.version,
            segment: change.data.segment,
          })}
        </p>
      ) : null}
    </section>
  );
}
