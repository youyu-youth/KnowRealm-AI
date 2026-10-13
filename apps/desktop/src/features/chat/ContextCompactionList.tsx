import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";

const COLUMNS = [
  "goals",
  "constraints",
  "decisions",
  "objects",
  "unfinished",
  "questions",
] as const;

export function ContextCompactionList({
  batches,
  showSummary = false,
  onReadSource,
}: {
  batches: components["schemas"]["CompactionOut"][];
  showSummary?: boolean;
  onReadSource?: (sourceId: string) => void;
}) {
  const { t } = useTranslation();
  if (batches.length === 0) return null;
  return (
    <section
      aria-label={t("chat.compaction.title")}
      className="flex flex-col gap-3"
    >
      {batches.map((batch) => (
        <div key={batch.id} className="border-border-subtle border-b pb-3">
          <p
            role="status"
            className="text-body text-muted-foreground break-words"
          >
            {t(`chat.compaction.status.${batch.status}`)} ·{" "}
            {t("chat.compaction.progress", {
              completed: batch.completed_chunks,
              total: batch.total_chunks,
              used: batch.requests_used,
              turnUsed: batch.turn_requests_used,
              allowance: batch.allowance,
            })}
          </p>
          {batch.error_code ? (
            <p className="text-body text-danger">
              {t(`errors.${batch.error_code}`)}
            </p>
          ) : null}
          {showSummary && batch.summary ? (
            <Collapsible>
              <CollapsibleTrigger render={<Button variant="ghost" />}>
                {t("chat.compaction.showSummary")}
              </CollapsibleTrigger>
              <CollapsibleContent className="flex flex-col gap-4 py-3">
                <p className="text-label text-muted-foreground">
                  {t("chat.compaction.summaryHint")}
                </p>
                <p className="text-label text-muted-foreground">
                  {t("chat.compaction.covered", {
                    count: batch.covered_message_ids.length,
                  })}
                </p>
                {COLUMNS.map((column) => (
                  <div key={column}>
                    <h2 className="text-body font-medium">
                      {t(`chat.compaction.columns.${column}`)}
                    </h2>
                    <ul className="text-body flex flex-col gap-2 pt-2">
                      {batch.summary?.[column].map((item, index) => (
                        <li key={index}>
                          <p className="break-words whitespace-pre-wrap">
                            {item.text}
                          </p>
                          <p className="text-label text-muted-foreground break-all">
                            {t("chat.compaction.sources")}{" "}
                            {onReadSource
                              ? item.source_ids.map((sourceId) => (
                                  <Button
                                    key={sourceId}
                                    variant="link"
                                    size="sm"
                                    className="h-auto max-w-full p-0 text-left break-all whitespace-normal"
                                    onClick={() => onReadSource(sourceId)}
                                  >
                                    {sourceId}
                                  </Button>
                                ))
                              : item.source_ids.join(", ")}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </CollapsibleContent>
            </Collapsible>
          ) : null}
        </div>
      ))}
    </section>
  );
}
