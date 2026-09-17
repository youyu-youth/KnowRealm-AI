import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  ConceptMastery,
  MasteryEvidenceItem,
} from "@/features/courses/api/types";
import { useConceptMasteryDetail } from "@/features/courses/api/queries";
import { ConceptMasteryBadge } from "@/features/courses/components/ConceptMasteryBadge";
import {
  masteryConfidenceLabelKeys,
  masteryPercentOf,
} from "@/features/courses/masteryStatus";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";

const RESULT_LABEL_KEYS = {
  CORRECT: "spaces.courseDetail.gps.detail.resultCorrect",
  WRONG: "spaces.courseDetail.gps.detail.resultWrong",
  PARTIAL: "spaces.courseDetail.gps.detail.resultPartial",
} as const;

/** Evidence 来源说明文案；无法定位时只保留来源说明与时间（不生成假链接）。 */
function evidenceSourceLabel(
  item: MasteryEvidenceItem,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const source = item.source;
  if (!source) return t("spaces.courseDetail.gps.detail.sourceUnknown");
  if (source.source_type === "QUIZ") {
    return t("spaces.courseDetail.gps.detail.sourceQuiz", {
      title: source.record_title,
    });
  }
  return source.sequence_no !== null
    ? t("spaces.courseDetail.gps.detail.sourceTest", {
        sequence: source.sequence_no,
      })
    : t("spaces.courseDetail.gps.detail.sourceTestPlain");
}

/** Concept 掌握详情弹窗：快照 + 参与计算的 Evidence，来源可跳回习题或模拟测试。 */
export function ConceptMasteryDetailDialog({
  courseId,
  concept,
  open,
  onOpenChange,
}: {
  courseId: string;
  concept: ConceptMastery | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const detail = useConceptMasteryDetail(
    courseId,
    open ? (concept?.concept_id ?? null) : null,
  );
  const format = (value: string) =>
    formatCourseMoment(
      value,
      t("spaces.time.yesterdayAt"),
      i18n.resolvedLanguage ?? "zh-CN",
    );
  const openSource = (item: MasteryEvidenceItem) => {
    const source = item.source;
    if (!source) return;
    onOpenChange(false);
    if (source.source_type === "QUIZ") {
      void navigate({
        to: "/records/$recordId",
        params: { recordId: source.record_id },
        search: { tab: "quiz" },
      });
    } else {
      void navigate({
        to: "/spaces/$courseId/tests/$testId",
        params: { courseId, testId: source.test_id },
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="truncate">
            {concept?.canonical_name}
          </DialogTitle>
          <DialogDescription>
            {t("spaces.courseDetail.gps.detail.description")}
          </DialogDescription>
        </DialogHeader>

        {detail.isPending ? (
          <p
            role="status"
            className="text-body text-ink-muted flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("spaces.courseDetail.gps.detail.loading")}
          </p>
        ) : null}

        {detail.isError ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-body text-ink-strong">
              {t("spaces.courseDetail.gps.detail.errorTitle")}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void detail.refetch()}
            >
              {t("spaces.courseDetail.gps.detail.retry")}
            </Button>
          </div>
        ) : null}

        {detail.data ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3">
              <ConceptMasteryBadge status={detail.data.snapshot.status} />
              {detail.data.snapshot.mastery_score !== null ? (
                <p className="text-section font-section text-ink-strong tabular-nums">
                  {t("spaces.courseDetail.gps.percentValue", {
                    percent: masteryPercentOf(
                      detail.data.snapshot.mastery_score,
                    ),
                  })}
                </p>
              ) : null}
            </div>

            <dl className="text-body-dense grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-ink-muted">
                {t("spaces.courseDetail.gps.detail.confidenceLabel")}
              </dt>
              <dd className="text-ink-strong">
                {detail.data.snapshot.confidence
                  ? t("spaces.courseDetail.gps.confidence", {
                      level: t(
                        masteryConfidenceLabelKeys[
                          detail.data.snapshot.confidence
                        ],
                      ),
                    })
                  : "—"}
              </dd>
              <dt className="text-ink-muted">
                {t("spaces.courseDetail.gps.detail.evidenceCountLabel")}
              </dt>
              <dd className="text-ink-strong tabular-nums">
                {detail.data.snapshot.evidence_count}
              </dd>
              <dt className="text-ink-muted">
                {t("spaces.courseDetail.gps.detail.lastVerifiedLabel")}
              </dt>
              <dd className="text-ink-strong">
                {detail.data.snapshot.last_verified_at
                  ? format(detail.data.snapshot.last_verified_at)
                  : "—"}
              </dd>
              <dt className="text-ink-muted">
                {t("spaces.courseDetail.gps.detail.lastPracticedLabel")}
              </dt>
              <dd className="text-ink-strong">
                {detail.data.snapshot.last_practiced_at
                  ? format(detail.data.snapshot.last_practiced_at)
                  : "—"}
              </dd>
            </dl>

            <div className="flex min-w-0 flex-col gap-1">
              <h4 className="text-label text-ink-muted">
                {t("spaces.courseDetail.gps.detail.evidenceListLabel")}
              </h4>
              {detail.data.evidences.length === 0 ? (
                <p className="text-body text-ink-muted">
                  {t("spaces.courseDetail.gps.detail.evidenceEmpty")}
                </p>
              ) : (
                <ol
                  aria-label={t(
                    "spaces.courseDetail.gps.detail.evidenceListLabel",
                  )}
                  className="-mx-1 max-h-[40vh] overflow-y-auto px-1"
                >
                  {detail.data.evidences.map((item) => (
                    <li
                      key={item.evidence_id}
                      className="border-border-subtle flex items-center gap-3 border-b py-2.5 last:border-b-0"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-body-dense text-ink-strong truncate">
                          {evidenceSourceLabel(item, t)}
                        </p>
                        <p className="text-label text-ink-muted mt-0.5">
                          {format(item.occurred_at)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-body-dense text-ink-strong tabular-nums">
                          {t("spaces.courseDetail.gps.percentValue", {
                            percent: masteryPercentOf(item.score),
                          })}
                        </p>
                        {item.result !== null &&
                        item.result in RESULT_LABEL_KEYS ? (
                          <p className="text-label text-ink-muted">
                            {/* in 守卫已确认键存在；RESULT_LABEL_KEYS 为有限白名单映射。 */}
                            {t(
                              RESULT_LABEL_KEYS[
                                item.result as keyof typeof RESULT_LABEL_KEYS
                              ],
                            )}
                          </p>
                        ) : null}
                      </div>
                      {item.source ? (
                        <Button
                          variant="outline"
                          size="icon-sm"
                          aria-label={t(
                            "spaces.courseDetail.gps.detail.openSource",
                          )}
                          onClick={() => openSource(item)}
                        >
                          <ArrowRight aria-hidden="true" />
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
