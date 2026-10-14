import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { ContextHistoryView } from "@/features/chat/ContextHistoryView";
import { useContextRuleChange } from "@/features/chat/useContextRuleChange";

export function ContextRulesView({
  sessionId,
  version,
  segment,
  rules,
  readOnly = false,
}: {
  sessionId: string;
  version: number;
  segment: number;
  rules: components["schemas"]["ContextRules"];
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const change = useContextRuleChange(sessionId);
  const [resetVersion, setResetVersion] = useState<number | null>(null);
  const resetButton = useRef<HTMLButtonElement>(null);
  return (
    <section
      aria-label={t("chat.contextRules.title")}
      className="mt-6 flex min-w-0 flex-col gap-4"
    >
      <h2 className="text-section">{t("chat.contextRules.title")}</h2>
      <p className="text-label text-muted-foreground">
        {t("chat.contextRules.summary", {
          segment,
          turns: rules.excluded_turn_ids?.length ?? 0,
          sources: rules.excluded_source_ids?.length ?? 0,
          included: rules.included_turn_ids?.length ?? 0,
        })}
      </p>
      {!readOnly ? (
        <>
          <p className="text-body text-muted-foreground">
            {t("chat.contextRules.hint")}
          </p>
          <Button
            ref={resetButton}
            variant="outline"
            className="w-fit"
            onClick={() => setResetVersion(version)}
            disabled={change.isPending}
          >
            {t("chat.contextRules.reset")}
          </Button>
          {rules.excluded_source_ids?.length ? (
            <ul className="flex flex-col gap-2">
              {rules.excluded_source_ids.map((source) => (
                <li
                  key={source}
                  className="flex min-w-0 flex-wrap items-center gap-2"
                >
                  <span className="text-label min-w-0 break-all">{source}</span>
                  <Button
                    variant="ghost"
                    disabled={change.isPending}
                    onClick={() =>
                      change.mutate({
                        expected_version: version,
                        action: "RESTORE_SOURCE",
                        source_id: source,
                      })
                    }
                  >
                    {t("chat.contextRules.restoreSource")}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          <ContextHistoryView
            sessionId={sessionId}
            version={version}
            segment={segment}
          />
        </>
      ) : null}
      {change.isError && resetVersion === null ? (
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
      <Dialog
        open={resetVersion !== null}
        onOpenChange={(open) => {
          if (!open) setResetVersion(null);
        }}
      >
        <DialogContent finalFocus={resetButton}>
          <DialogHeader>
            <DialogTitle>{t("chat.contextRules.reset")}</DialogTitle>
            <DialogDescription>
              {t("chat.contextRules.resetHint")}
            </DialogDescription>
          </DialogHeader>
          {change.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{change.error.message}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setResetVersion(null)}>
              {t("chat.contextRules.cancel")}
            </Button>
            <Button
              variant="outline"
              disabled={change.isPending}
              onClick={() => {
                if (resetVersion !== null)
                  change.mutate(
                    { expected_version: resetVersion, action: "RESET" },
                    { onSuccess: () => setResetVersion(null) },
                  );
              }}
            >
              {t("chat.contextRules.confirmReset")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
