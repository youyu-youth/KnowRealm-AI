import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { ContextPinTextForm } from "@/features/chat/ContextPinTextForm";
import { useContextPinChange } from "@/features/chat/useContextPinChange";

export function ContextPinsView({
  sessionId,
  version,
  pins,
  readOnly = false,
}: {
  sessionId: string;
  version: number;
  pins: components["schemas"]["ContextPinOut"][];
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const change = useContextPinChange(sessionId);
  const [editing, setEditing] = useState<
    components["schemas"]["ContextPinOut"] | null
  >(null);
  return (
    <section
      aria-label={t("chat.pins.title")}
      className="mt-6 flex min-w-0 flex-col gap-4"
    >
      <h2 className="text-section">{t("chat.pins.title")}</h2>
      {!readOnly ? (
        <p className="text-label text-muted-foreground">
          {t("chat.pins.nextHint")}
        </p>
      ) : null}
      {pins.length === 0 ? (
        <p className="text-body text-muted-foreground">
          {t("chat.pins.empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {pins.map((pin) => (
            <li
              key={pin.id}
              className="border-border-subtle flex min-w-0 flex-col gap-2 border-b pb-4"
            >
              <p className="text-body break-words">{pin.title}</p>
              <p className="text-label text-muted-foreground break-words">
                {t(`chat.pins.modes.${pin.mode}`)} ·{" "}
                {t(`chat.pins.status.${pin.status}`)}
                {readOnly
                  ? ` · ${t(pin.injected ? "chat.pins.injected" : "chat.pins.notInjected")}`
                  : ""}
              </p>
              {pin.source_id ? (
                <p className="text-label text-muted-foreground break-all">
                  {pin.source_id} · {pin.source_version}
                </p>
              ) : null}
              {pin.content ? (
                <Collapsible>
                  <CollapsibleTrigger render={<Button variant="ghost" />}>
                    {t("chat.pins.showText")}
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <p className="text-body break-words whitespace-pre-wrap">
                      {pin.content}
                    </p>
                  </CollapsibleContent>
                </Collapsible>
              ) : null}
              {pin.reason ? (
                <p role="status" className="text-label text-muted-foreground">
                  {t(`errors.${pin.reason}`)}
                </p>
              ) : null}
              {!readOnly ? (
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={change.isPending}
                    onClick={() => {
                      if (pin.mode === "TEXT") {
                        setEditing(pin);
                      } else
                        void navigate({
                          to: "/chat-context/$sessionId",
                          params: { sessionId },
                          search: {
                            view: "sources",
                            source: pin.source_id ?? undefined,
                            pin: pin.id,
                            pinVersion: version,
                          },
                        });
                    }}
                  >
                    {t("chat.pins.update")}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={change.isPending}
                    onClick={() =>
                      change.mutate(
                        {
                          action: "REMOVE",
                          content: "",
                          offset: 0,
                          pin_id: pin.id,
                          expected_version: version,
                        },
                        {
                          onSuccess: () => {
                            if (editing?.id === pin.id) setEditing(null);
                          },
                        },
                      )
                    }
                  >
                    {t("chat.pins.remove")}
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {!readOnly ? (
        <ContextPinTextForm
          key={editing?.id ?? "new"}
          sessionId={sessionId}
          version={version}
          pin={editing}
          onCancel={() => setEditing(null)}
        />
      ) : null}
      {change.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{change.error.message}</AlertDescription>
        </Alert>
      ) : null}
      {change.isSuccess ? (
        <p role="status" className="text-label text-muted-foreground">
          {t("chat.pins.saved", { version: change.data.version })}
        </p>
      ) : null}
    </section>
  );
}
