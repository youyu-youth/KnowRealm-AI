import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  studyApi,
  studyKey,
  useRecordStudy,
} from "@/features/learningPlan/api/study";
import { useCompletePlanItem } from "@/features/learningPlan/api/learningPlan";

import { StudySourcePicker } from "@/features/learningPlan/components/StudySourcePicker";

export function RecordStudyPage({ itemId }: { itemId: string }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selecting, setSelecting] = useState(false);
  const study = useRecordStudy(itemId);
  const complete = useCompletePlanItem();
  const startRef = useRef<HTMLButtonElement>(null);
  const requestId = useRef<string | null>(null);
  const hasSource = !!study.data?.source;
  useEffect(() => {
    if (hasSource) startRef.current?.focus();
  }, [hasSource]);
  const start = useMutation({
    mutationFn: (recordId: string) => {
      requestId.current ??= crypto.randomUUID();
      return studyApi.start(itemId, {
        request_id: requestId.current,
        record_id: recordId,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: studyKey(itemId) }),
    onError: () =>
      void queryClient.invalidateQueries({ queryKey: studyKey(itemId) }),
  });

  if (study.isPending) return <p role="status">{t("learningPlan.loading")}</p>;
  if (study.isError)
    return (
      <div role="alert" className="px-content py-8">
        <p>{study.error.message}</p>
        <Button onClick={() => void study.refetch()}>
          {t("learningPlan.retry")}
        </Button>
      </div>
    );
  const data = study.data;
  const error = complete.error ?? start.error;
  const choosing = selecting || data.source_status !== "AVAILABLE";
  return (
    <section className="px-content text-body flex min-w-0 flex-col gap-5 py-8">
      <Link
        to="/spaces/$courseId"
        params={{ courseId: data.course_id }}
        search={{ tab: "plan", planItem: itemId }}
        className="text-muted-foreground focus-visible:outline-ring rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        {t("study.backToPlan")}
      </Link>
      <h1 className="text-headline font-headline text-ink-strong break-words">
        {data.item.content}
      </h1>
      <p className="text-muted-foreground">{t("study.honestBoundary")}</p>
      {!data.editable ? <p role="status">{t("study.readonly")}</p> : null}
      {data.source ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="min-w-0 break-words">{data.source.title}</p>
          {data.source.read_only ? (
            <span className="text-muted-foreground">
              {t("study.sharedReadonly")}
            </span>
          ) : null}
          {data.editable ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelecting(!selecting)}
            >
              {t(selecting ? "learningPlan.edit.cancel" : "study.changeSource")}
            </Button>
          ) : null}
        </div>
      ) : (
        <p role="status">
          {t(
            data.source_status === "MISSING"
              ? "study.missing"
              : "study.unavailable",
          )}
        </p>
      )}
      {choosing && data.editable ? (
        <StudySourcePicker
          itemId={itemId}
          courseId={data.course_id}
          planId={data.plan_id}
          onSaved={() => {
            setSelecting(false);
            requestId.current = null;
          }}
        />
      ) : null}
      {data.started_at ? (
        <p className="text-muted-foreground" role="status">
          {t("study.lastStarted", {
            time: new Date(data.started_at).toLocaleString(
              i18n.resolvedLanguage,
            ),
            tab: t(
              `record.detail.tabs.${data.tab === "knowledge-points" ? "knowledgePoints" : data.tab}`,
            ),
          })}
        </p>
      ) : (
        <p className="text-muted-foreground">{t("study.notStarted")}</p>
      )}
      <div className="flex flex-wrap gap-3">
        {data.editable && data.source ? (
          <Button
            ref={startRef}
            disabled={start.isPending || selecting}
            onClick={() => {
              if (data.source)
                start.mutate(data.source.record_id, {
                  onSuccess: (result) => {
                    if (!result.source || !result.visit_id) return;
                    void navigate({
                      to: "/records/$recordId",
                      params: { recordId: result.source.record_id },
                      search: {
                        tab: result.tab === "summary" ? undefined : result.tab,
                        studyItem: itemId,
                        studyVisit: result.visit_id,
                      },
                    });
                  },
                });
            }}
          >
            {t(data.started_at ? "study.continue" : "study.start")}
          </Button>
        ) : null}
        {data.editable && data.item.status === "PENDING" ? (
          <Button
            variant="outline"
            disabled={complete.isPending}
            onClick={() =>
              complete.mutate({
                courseId: data.course_id,
                planId: data.plan_id,
                itemId,
              })
            }
          >
            {t("study.complete")}
          </Button>
        ) : null}
        {data.item.status === "DONE" ? <p>{t("study.completed")}</p> : null}
      </div>
      {error ? (
        <p role="alert" className="text-destructive">
          {error.message}
        </p>
      ) : null}
    </section>
  );
}
