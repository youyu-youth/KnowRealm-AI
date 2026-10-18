import { FileText, SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { PracticeState } from "@/features/learningPlan/api/practice";

export function PracticeRequirementsPanel({
  state,
  editing,
  onEdit,
}: {
  state: PracticeState;
  editing: boolean;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  const req = state.requirements;
  if (!req) return null;

  return (
    <aside className="practice-requirements min-w-0 space-y-5">
      <div className="space-y-2">
        <h2 className="text-ink text-base font-semibold">
          {t(
            state.round
              ? "practice.workspace.next"
              : "practice.workspace.requirements",
          )}
        </h2>
        <p className="text-label text-ink-muted">
          {t("practice.revision", { revision: req.revision })}
        </p>
      </div>
      <div className="space-y-3">
        <p className="text-body text-ink font-medium wrap-anywhere">
          {req.topic}
        </p>
        <p className="text-body text-ink tabular-nums">
          {t("practice.target", { count: req.question_count })}
        </p>
        <div className="flex flex-wrap gap-2">
          {req.question_types.map((type) => (
            <span
              key={type}
              className="text-label bg-surface-strong text-ink-neutral rounded-sm px-2 py-1"
            >
              {t(`practice.type.${type}`)}
            </span>
          ))}
        </div>
      </div>
      <details className="practice-disclosure">
        <summary>
          {t("practice.workspace.sourceCount", {
            count: req.record_ids.length,
          })}
        </summary>
        <ul className="mt-3 space-y-3">
          {req.record_ids.map((id) => (
            <li
              key={id}
              className="text-body text-ink-muted flex items-start gap-2"
            >
              <FileText className="mt-1 size-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 wrap-anywhere">
                {state.sources.find((source) => source.record_id === id)
                  ?.title ?? t("practice.sourceUnavailable")}
              </span>
            </li>
          ))}
        </ul>
      </details>
      {state.requirements_stale ? (
        <p role="alert" className="text-body text-warning-foreground">
          {t("practice.stale")}
        </p>
      ) : null}
      {state.editable ? (
        <div className="space-y-3">
          {state.round ? (
            <p className="text-label text-ink-muted">
              {t("practice.recovery.nextRequirements")}
            </p>
          ) : null}
          <Button
            variant="outline"
            onClick={onEdit}
            aria-expanded={editing}
            aria-controls="practice-requirements-editor"
            className="h-auto min-h-9 w-full whitespace-normal"
          >
            <SlidersHorizontal aria-hidden="true" />
            {t(editing ? "practice.closeEdit" : "practice.edit")}
          </Button>
        </div>
      ) : null}
    </aside>
  );
}
