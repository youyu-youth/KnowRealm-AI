import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { ContextBudgetDetails } from "@/features/chat/ContextBudgetDetails";

export function ContextRequestList({
  requests,
}: {
  requests: components["schemas"]["ModelRequestOut"][];
}) {
  const { t, i18n } = useTranslation();
  if (requests.length === 0)
    return (
      <p className="text-body text-muted-foreground">
        {t("chat.contextView.noActual")}
      </p>
    );
  return (
    <div className="flex flex-col gap-4">
      {requests.map((request, index) => (
        <Collapsible
          key={request.id}
          defaultOpen={index === requests.length - 1}
          className="border-border-subtle border-b pb-4"
        >
          <CollapsibleTrigger
            render={
              <Button
                variant="ghost"
                className="h-auto w-full justify-between text-start whitespace-normal"
              />
            }
          >
            <span>
              {t("chat.contextView.request", { count: index + 1 })} ·{" "}
              {t(`chat.contextView.status.${request.status}`)}
            </span>
            <span className="text-muted-foreground tabular-nums">
              {request.estimate.input_tokens.toLocaleString(i18n.language)}
            </span>
          </CollapsibleTrigger>
          <CollapsibleContent className="px-2 pt-4">
            <ContextBudgetDetails estimate={request.estimate} />
            <p className="text-label text-muted-foreground mt-4">
              {t("chat.contextView.usage", {
                input:
                  request.usage?.input_tokens?.toLocaleString(i18n.language) ??
                  t("chat.contextView.unknown"),
                output:
                  request.usage?.output_tokens?.toLocaleString(i18n.language) ??
                  t("chat.contextView.unknown"),
              })}
            </p>
            {request.error_code ? (
              <p className="text-body text-danger mt-3">
                {t(`errors.${request.error_code}`)}
              </p>
            ) : null}
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
}
