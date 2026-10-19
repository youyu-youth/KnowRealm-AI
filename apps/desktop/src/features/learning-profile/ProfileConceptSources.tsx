import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useConceptSources } from "@/features/courses/api/courseBrain";
import {
  anchorJumpTarget,
  knowledgePointJumpTarget,
} from "@/features/courses/courseBrainJump";

export function ProfileConceptSources({
  courseId,
  conceptId,
}: {
  courseId: string;
  conceptId: string;
}) {
  const { t } = useTranslation();
  const query = useConceptSources(courseId, conceptId);
  if (query.isPending)
    return (
      <p role="status" className="text-body text-ink-muted py-5">
        {t("learningProfile.loading")}
      </p>
    );
  if (query.isError)
    return (
      <div role="alert">
        <p className="text-body text-destructive">
          {t("learningProfile.sources.error")}
        </p>
        <Button
          variant="outline"
          className="mt-3"
          onClick={() => void query.refetch()}
        >
          {t("learningProfile.retry")}
        </Button>
      </div>
    );
  const sources = query.data;
  if (!sources.anchors.length && !sources.knowledge_points.length)
    return (
      <p className="text-body text-ink-muted py-5">
        {t("learningProfile.sources.empty")}
      </p>
    );
  return (
    <ul className="divide-border-subtle divide-y">
      {sources.anchors.map((anchor) => {
        const target = anchorJumpTarget(anchor);
        return (
          <li key={anchor.anchor_id} className="py-4">
            <p className="text-body font-section text-ink">
              {anchor.record_title ?? t("learningProfile.sources.chat")}
            </p>
            {anchor.quote ? (
              <p className="text-body-dense text-ink-muted mt-2 leading-relaxed break-words">
                {anchor.quote}
              </p>
            ) : null}
            {target ? (
              <Link
                {...target}
                className="text-label text-ink-muted mt-3 inline-block underline underline-offset-4"
              >
                {t("learningProfile.sources.open")}
              </Link>
            ) : null}
          </li>
        );
      })}
      {sources.knowledge_points.map((point) => (
        <li key={point.knowledge_point_id} className="py-4">
          <p className="text-body font-section text-ink">
            {point.knowledge_point_name}
          </p>
          <p className="text-label text-ink-muted mt-1">{point.record_title}</p>
          <Link
            {...knowledgePointJumpTarget(point)}
            className="text-label text-ink-muted mt-3 inline-block underline underline-offset-4"
          >
            {t("learningProfile.sources.open")}
          </Link>
        </li>
      ))}
    </ul>
  );
}
