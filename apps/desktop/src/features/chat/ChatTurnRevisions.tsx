import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ChatMessageTurn } from "@/features/chat/api/types";

export function ChatTurnRevisions({
  revisions,
}: {
  revisions: ChatMessageTurn["revisions"];
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!revisions?.length) return null;
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="text-muted-foreground min-w-0"
    >
      <CollapsibleTrigger
        render={<Button variant="ghost" size="sm" />}
        className="h-auto max-w-full cursor-pointer gap-2 py-1.5 whitespace-normal"
      >
        <History aria-hidden="true" />
        <span className="min-w-0 text-left">
          {t("chat.turn.revisions.view", { count: revisions.length })}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={open ? "shrink-0 rotate-180" : "shrink-0"}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol
          aria-label={t("chat.turn.revisions.history")}
          className="flex min-w-0 flex-col gap-4 px-2 py-2"
        >
          {revisions.map((revision) => (
            <li
              key={`${revision.output_revision}:${revision.replaces_segment}`}
              className="flex min-w-0 flex-col gap-2"
            >
              <p className="text-label">
                {t("chat.turn.revisions.previous", {
                  revision: revision.previous_revision,
                })}
              </p>
              <p className="text-body break-words whitespace-pre-wrap">
                {revision.previous_text}
              </p>
              <p className="text-label">
                {t("chat.turn.revisions.regenerated", {
                  revision: revision.output_revision,
                })}
              </p>
              <p className="text-body text-foreground break-words whitespace-pre-wrap">
                {revision.regenerated_text || t("chat.turn.revisions.pending")}
              </p>
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
