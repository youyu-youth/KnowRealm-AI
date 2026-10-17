import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  studyApi,
  studyKey,
  useRecordStudy,
  type StudyTab,
} from "@/features/learningPlan/api/study";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";

export function RecordStudySession({
  itemId,
  visitId,
  recordId,
  tab,
  onTabChange,
}: {
  itemId: string;
  visitId: string;
  recordId: string;
  tab: StudyTab;
  onTabChange: (tab: StudyTab) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const study = useRecordStudy(itemId);
  const { refetch } = study;
  useEffect(() => {
    const refresh = () => void refetch();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refetch]);
  const save = useMutation({
    scope: { id: `study-tab-${itemId}` },
    mutationFn: (nextTab: StudyTab) =>
      studyApi.tab(itemId, {
        visit_id: visitId,
        record_id: recordId,
        tab: nextTab,
      }),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: studyKey(itemId) }),
  });
  const back = (
    <Link
      to="/plan-items/$itemId/study"
      params={{ itemId }}
      className="text-muted-foreground focus-visible:outline-ring rounded-sm hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      {t("study.backToItem")}
    </Link>
  );
  if (study.isPending) return <p role="status">{t("learningPlan.loading")}</p>;
  if (study.isError)
    return (
      <section className="px-content grid gap-4 py-8">
        {back}
        <p role="alert">{study.error.message}</p>
        <Button onClick={() => void study.refetch()}>
          {t("learningPlan.retry")}
        </Button>
      </section>
    );
  const data = study.data;
  if (
    !data.editable ||
    data.visit_id !== visitId ||
    data.source?.record_id !== recordId
  ) {
    return (
      <section className="px-content grid gap-4 py-8">
        {back}
        <p role="alert">{t("study.staleVisit")}</p>
      </section>
    );
  }
  return (
    <>
      {save.error ? (
        <p role="alert" className="text-destructive px-content pt-4">
          {save.error.message}
        </p>
      ) : null}
      {save.isPending ? (
        <p role="status" className="text-muted-foreground px-content pt-4">
          {t("study.savingTab")}
        </p>
      ) : null}
      <RecordDetailPage
        key={data.source.read_only ? "shared" : "owned"}
        requestCourseId={data.course_id}
        recordId={recordId}
        tab={tab}
        readOnly={data.source.read_only}
        backLink={back}
        onTabChange={(next) =>
          save.mutate(next, { onSuccess: (result) => onTabChange(result.tab) })
        }
        onDeleted={() =>
          navigate({ to: "/plan-items/$itemId/study", params: { itemId } })
        }
      />
    </>
  );
}
