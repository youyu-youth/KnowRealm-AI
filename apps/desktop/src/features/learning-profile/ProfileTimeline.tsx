import { Check, ChevronRight, CircleHelp, FileCheck2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { ConceptMastery } from "@/features/courses/api/types";
import { ConceptMasteryBadge } from "@/features/courses/components/ConceptMasteryBadge";
import { cn } from "@/lib/utils";

export function ProfileTimeline({
  concepts,
  selectedId,
  expanded = false,
  onSelect,
  onExpand,
}: {
  concepts: ConceptMastery[];
  selectedId?: string;
  expanded?: boolean;
  onSelect: (id: string) => void;
  onExpand?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const practiced = concepts
    .filter((concept) => concept.last_practiced_at)
    .sort(
      (first, second) =>
        Date.parse(second.last_practiced_at ?? "") -
        Date.parse(first.last_practiced_at ?? ""),
    );
  const pending = concepts.filter((concept) => !concept.last_practiced_at);
  const visible = expanded
    ? [...practiced, ...pending]
    : [
        ...practiced.slice(0, 2),
        ...(pending.length ? pending.slice(0, 1) : practiced.slice(2, 3)),
      ];
  return (
    <section
      className="min-w-0"
      aria-labelledby={
        expanded ? "profile-history-title" : "profile-timeline-title"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id={expanded ? "profile-history-title" : "profile-timeline-title"}
          className="text-profile-section font-section text-ink-strong"
        >
          {t(
            expanded
              ? "learningProfile.timeline.history"
              : "learningProfile.timeline.title",
          )}
        </h2>
        {onExpand ? (
          <Button variant="outline" size="sm" onClick={onExpand}>
            {t("learningProfile.timeline.expand")}
            <ChevronRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      {expanded ? (
        <p className="text-label text-ink-muted mt-2">
          {t("learningProfile.timeline.scope")}
        </p>
      ) : null}
      {visible.length ? (
        <ol
          className={cn(
            "profile-timeline mt-5",
            expanded && "profile-timeline-expanded",
          )}
        >
          {visible.map((concept) => {
            const pending = !concept.last_practiced_at;
            const Icon = pending
              ? CircleHelp
              : concept.status === "STABLE"
                ? Check
                : FileCheck2;
            return (
              <li key={concept.concept_id} className="min-w-0">
                <button
                  type="button"
                  aria-pressed={selectedId === concept.concept_id}
                  onClick={() => onSelect(concept.concept_id)}
                  className="profile-timeline-event group focus-visible:ring-ring relative flex h-full w-full min-w-0 gap-3 rounded-sm p-3 pb-7 text-left focus-visible:ring-2"
                >
                  <span className="border-ink-muted text-ink bg-paper flex size-9 shrink-0 items-center justify-center rounded-full border">
                    <Icon className="size-5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-label text-ink-muted">
                      {pending
                        ? t("learningProfile.timeline.pending")
                        : new Date(
                            concept.last_practiced_at ?? "",
                          ).toLocaleDateString(i18n.resolvedLanguage, {
                            month: "long",
                            day: "numeric",
                            weekday: "short",
                          })}
                    </p>
                    <p className="text-body font-section text-ink-strong mt-2 break-words">
                      {concept.canonical_name}
                    </p>
                    <p className="text-label text-ink-muted mt-2 leading-relaxed">
                      {pending
                        ? t("learningProfile.timeline.pendingHint")
                        : t("learningProfile.timeline.evidence", {
                            count: concept.evidence_count,
                          })}
                    </p>
                    <ConceptMasteryBadge
                      status={concept.status}
                      className="mt-3"
                    />
                  </div>
                  <span
                    className="profile-timeline-dot bg-ink-muted border-paper group-aria-pressed:ring-ink-faint absolute bottom-0 left-7 size-3 rounded-full border-2 group-aria-pressed:ring-2"
                    aria-hidden="true"
                  />
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-body text-ink-muted py-8">
          {t("learningProfile.timeline.empty")}
        </p>
      )}
    </section>
  );
}
