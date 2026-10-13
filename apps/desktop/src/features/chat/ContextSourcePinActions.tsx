import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { useContextPinChange } from "@/features/chat/useContextPinChange";

export function ContextSourcePinActions({
  sessionId,
  original,
  pinId,
  pinVersion,
}: {
  sessionId: string;
  original: components["schemas"]["ContextReadOut"];
  pinId?: string;
  pinVersion?: number;
}) {
  const { t } = useTranslation();
  const context = useQuery({
    queryKey: chatKeys.context(sessionId, { content: "", web_search: false }),
    queryFn: () => contextApi.get(sessionId),
    staleTime: 0,
  });
  const change = useContextPinChange(sessionId);
  const [expectedVersion, setExpectedVersion] = useState(pinVersion);
  const [selection, setSelection] = useState({
    start: 0,
    end: original.content.length,
  });
  const pin = (mode: "SNIPPET" | "OBJECT") => {
    if (!context.data) return;
    change.mutate(
      {
        expected_version: expectedVersion ?? context.data.version,
        action: pinId ? "UPDATE" : "ADD",
        pin_id: pinId,
        mode,
        source_id: original.source.source_id,
        source_version: original.source.version,
        content:
          mode === "SNIPPET"
            ? original.content.slice(selection.start, selection.end)
            : "",
        offset: original.offset + selection.start,
      },
      { onSuccess: (result) => setExpectedVersion(result.version) },
    );
  };
  const disabled = change.isPending || !context.isSuccess;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <Field>
        <FieldLabel htmlFor="pin-source-selection">
          {t("chat.pins.selectionLabel")}
        </FieldLabel>
        <Textarea
          id="pin-source-selection"
          readOnly
          value={original.content}
          onSelect={(event) =>
            setSelection({
              start: event.currentTarget.selectionStart,
              end: event.currentTarget.selectionEnd,
            })
          }
        />
      </Field>
      <p className="text-label text-muted-foreground">
        {t("chat.pins.selectionHint", {
          count: selection.end - selection.start,
        })}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={disabled || selection.end <= selection.start}
          onClick={() => pin("SNIPPET")}
        >
          {t(pinId ? "chat.pins.updateSnippet" : "chat.pins.addSnippet")}
        </Button>
        {original.source.kind === "record" ||
        original.source.kind === "library" ? (
          <Button
            variant="ghost"
            disabled={disabled}
            onClick={() => pin("OBJECT")}
          >
            {t(pinId ? "chat.pins.updateObject" : "chat.pins.addObject")}
          </Button>
        ) : null}
      </div>
      <p className="text-label text-muted-foreground">
        {t("chat.pins.objectHint")}
      </p>
      {context.isError || change.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {(change.error ?? context.error)?.message}
          </AlertDescription>
          <Button
            variant="outline"
            onClick={() => {
              void context.refetch().then((result) => {
                if (result.isSuccess && result.data) {
                  setExpectedVersion(result.data.version);
                  change.reset();
                }
              });
            }}
          >
            {t("chat.pins.retryLatest")}
          </Button>
        </Alert>
      ) : null}
      {change.isSuccess ? (
        <p role="status" className="text-label text-muted-foreground">
          {t("chat.pins.saved", { version: change.data.version })}
        </p>
      ) : null}
    </div>
  );
}
