import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useContextPinChange } from "@/features/chat/useContextPinChange";

export function ContextPinTextForm({
  sessionId,
  version,
  pin,
  onCancel,
}: {
  sessionId: string;
  version: number;
  pin: components["schemas"]["ContextPinOut"] | null;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const change = useContextPinChange(sessionId);
  const [text, setText] = useState(pin?.content ?? "");
  const [draftVersion, setDraftVersion] = useState<number | null>(
    pin ? version : null,
  );
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        change.mutate(
          {
            action: pin ? "UPDATE" : "ADD",
            pin_id: pin?.id,
            expected_version: draftVersion ?? version,
            mode: "TEXT",
            content: text,
            offset: 0,
          },
          {
            onSuccess: (result) => {
              if (!pin) setText("");
              setDraftVersion(pin ? result.version : null);
            },
          },
        );
      }}
    >
      <Field>
        <FieldLabel htmlFor="context-pin-text">
          {t("chat.pins.textLabel")}
        </FieldLabel>
        <Textarea
          id="context-pin-text"
          value={text}
          maxLength={8000}
          disabled={change.isPending}
          onChange={(event) => {
            setDraftVersion((current) => current ?? version);
            setText(event.target.value);
          }}
          placeholder={t("chat.pins.textPlaceholder")}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={change.isPending || !text.trim()}>
          {t(
            change.isPending
              ? "chat.pins.saving"
              : pin
                ? "chat.pins.update"
                : "chat.pins.add",
          )}
        </Button>
        {pin ? (
          <Button
            type="button"
            variant="ghost"
            disabled={change.isPending}
            onClick={onCancel}
          >
            {t("chat.pins.cancelEdit")}
          </Button>
        ) : null}
      </div>
      {change.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{change.error.message}</AlertDescription>
          <Button
            variant="outline"
            onClick={() => {
              setDraftVersion(version);
              change.reset();
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
    </form>
  );
}
