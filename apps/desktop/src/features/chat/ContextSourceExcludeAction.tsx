import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { useContextRuleChange } from "@/features/chat/useContextRuleChange";

export function ContextSourceExcludeAction({
  sessionId,
  sourceId,
  sourceVersion,
}: {
  sessionId: string;
  sourceId: string;
  sourceVersion: string;
}) {
  const { t } = useTranslation();
  const context = useQuery({
    queryKey: chatKeys.context(sessionId, { content: "", web_search: false }),
    queryFn: () => contextApi.get(sessionId),
    staleTime: 0,
  });
  const change = useContextRuleChange(sessionId);
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        className="w-fit"
        disabled={!context.data || change.isPending}
        onClick={() => {
          if (context.data)
            change.mutate({
              expected_version: context.data.version,
              action: "EXCLUDE_SOURCE",
              source_id: sourceId,
              source_version: sourceVersion,
            });
        }}
      >
        {t("chat.contextRules.excludeSource")}
      </Button>
      {context.isError || change.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {(context.error ?? change.error)?.message}
          </AlertDescription>
          <Button variant="ghost" onClick={() => void context.refetch()}>
            {t("chat.retry")}
          </Button>
        </Alert>
      ) : null}
    </div>
  );
}
