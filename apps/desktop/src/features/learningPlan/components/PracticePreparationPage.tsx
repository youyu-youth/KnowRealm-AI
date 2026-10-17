import { PracticeRequirementsForm } from "@/features/learningPlan/components/PracticeRequirementsForm";
import { PracticePreparationResult } from "@/features/learningPlan/components/PracticePreparationResult";
import { PracticeRoundCard } from "@/features/learningPlan/components/PracticeRoundCard";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, buttonVariants } from "@/components/ui/button";
import { practiceApi, practiceKey } from "@/features/learningPlan/api/practice";
import { ApiError } from "@/services/http/client";

export function PracticePreparationPage({ itemId }: { itemId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const request = useRef<{ revision: number; id: string } | null>(null);
  const roundRequest = useRef<string | null>(null);
  const prepareButton = useRef<HTMLButtonElement>(null);
  const focusAfterSave = useRef(false);
  const query = useQuery({
    queryKey: practiceKey(itemId),
    queryFn: () => practiceApi.state(itemId),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.preparations.some((prep) =>
        ["PENDING", "RUNNING"].includes(prep.status),
      ) || (query.state.data?.round?.status === "GRADING" ? true : false)
        ? 1000
        : false,
  });
  useEffect(() => {
    if (focusAfterSave.current && query.data?.requirements) {
      prepareButton.current?.focus();
      focusAfterSave.current = false;
    }
  }, [query.data?.requirements]);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: practiceKey(itemId) });
  const prepare = useMutation({
    mutationFn: (revision: number) => {
      if (request.current?.revision !== revision)
        request.current = { revision, id: crypto.randomUUID() };
      return practiceApi.prepare(itemId, revision, request.current.id);
    },
    onSuccess: () => {
      request.current = null;
      return refresh();
    },
  });
  const startRound = useMutation({
    mutationFn: (revision: number) => {
      roundRequest.current ??= crypto.randomUUID();
      return practiceApi.startRound(itemId, revision, roundRequest.current);
    },
    onSuccess: () => refresh(),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => practiceApi.cancel(itemId, id),
    onSuccess: refresh,
  });
  if (query.isPending) return <p role="status">{t("practice.loading")}</p>;
  if (!query.data)
    return (
      <div role="alert">
        <p>{t("practice.failed")}</p>
        <Button onClick={() => void query.refetch()}>
          {t("practice.retry")}
        </Button>
      </div>
    );
  const state = query.data;
  const req = state.requirements;
  const latest = state.preparations[0];
  const active = state.preparations.some((prep) =>
    ["PENDING", "RUNNING"].includes(prep.status),
  );
  const error = prepare.error ?? cancel.error ?? startRound.error;
  const readyToStart =
    !state.round &&
    state.editable &&
    !state.requirements_stale &&
    req !== null &&
    latest !== undefined &&
    latest.status === "SUCCEEDED" &&
    latest.outcome === "READY";
  return (
    <section className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <Link
        to="/spaces/$courseId"
        params={{ courseId: state.course_id }}
        search={{ tab: "plan" }}
        className={buttonVariants({ variant: "ghost", size: "sm" })}
      >
        {t("practice.back")}
      </Link>
      <Button variant="ghost" size="sm" onClick={() => void query.refetch()}>
        {t("practice.refresh")}
      </Button>
      <header className="space-y-2">
        <h1 className="text-headline text-ink">{t("practice.title")}</h1>
        <p className="text-body text-ink-muted wrap-anywhere">
          {state.plan_content}
        </p>
      </header>
      {state.round ? (
        <PracticeRoundCard round={state.round} courseId={state.course_id} />
      ) : null}
      {req ? (
        <div className="space-y-2">
          <h2 className="text-section text-ink">
            {t("practice.revision", { revision: req.revision })}
          </h2>
          <p className="text-body wrap-anywhere">
            {req.topic} · {t("practice.target", { count: req.question_count })}
          </p>
          <p className="text-label text-ink-muted">
            {req.question_types
              .map((type) => t(`practice.type.${type}`))
              .join(" · ")}
          </p>
          <ul className="text-body list-inside list-disc">
            {req.record_ids.map((id) => (
              <li key={id}>
                {state.sources.find((source) => source.record_id === id)
                  ?.title ?? t("practice.sourceUnavailable")}
              </li>
            ))}
          </ul>
          {state.requirements_stale ? (
            <p role="alert">{t("practice.stale")}</p>
          ) : null}
          {state.editable ? (
            <div className="flex flex-wrap gap-2">
              <Button
                ref={prepareButton}
                disabled={
                  active || prepare.isPending || state.requirements_stale
                }
                onClick={() => prepare.mutate(req.revision)}
              >
                {t(latest ? "practice.retry" : "practice.prepare")}
              </Button>
              {readyToStart ? (
                <Button
                  disabled={startRound.isPending}
                  onClick={() => startRound.mutate(req.revision)}
                >
                  {t("practice.round.start")}
                </Button>
              ) : null}
              <Button
                variant="outline"
                onClick={() => setEditing((value) => !value)}
              >
                {t(editing ? "practice.closeEdit" : "practice.edit")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {state.editable && (!req || editing) ? (
        <PracticeRequirementsForm
          key={state.item_id}
          state={state}
          reload={() => query.refetch().then((result) => result.data)}
          saved={() => {
            focusAfterSave.current = true;
            setEditing(false);
            void refresh();
          }}
        />
      ) : null}
      {error ? (
        <p role="alert" className="text-body text-danger">
          {error instanceof ApiError
            ? t(`errors.${error.code}`, { defaultValue: t("practice.failed") })
            : t("practice.failed")}
        </p>
      ) : null}
      {latest ? (
        <PracticePreparationResult
          latest={latest}
          cancelPending={cancel.isPending}
          onCancel={(id) => cancel.mutate(id)}
        />
      ) : null}
      <p className="text-label text-ink-muted">{t("practice.stageHint")}</p>
    </section>
  );
}
