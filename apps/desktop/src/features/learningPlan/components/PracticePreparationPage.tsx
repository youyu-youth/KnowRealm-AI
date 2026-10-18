import { PracticeRequirementsForm } from "@/features/learningPlan/components/PracticeRequirementsForm";
import { PracticePreparationResult } from "@/features/learningPlan/components/PracticePreparationResult";
import { PracticeRoundCard } from "@/features/learningPlan/components/PracticeRoundCard";
import { PracticeRequirementsPanel } from "@/features/learningPlan/components/PracticeRequirementsPanel";
import { ArrowLeft, ArrowRight, RefreshCw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  practiceApi,
  practiceKey,
  type PracticeRound,
} from "@/features/learningPlan/api/practice";
import { quizTestKeys } from "@/features/quiz-tests/api/keys";
import { ApiError } from "@/services/http/client";
import "@/features/learningPlan/components/PracticePreparation.css";

export function PracticePreparationPage({
  itemId,
  selectedRoundId,
}: {
  itemId: string;
  selectedRoundId?: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [restartConfirmation, setRestartConfirmation] =
    useState<PracticeRound | null>(null);
  const request = useRef<{ key: string; id: string } | null>(null);
  const roundRequest = useRef<{ preparationId: string; id: string } | null>(
    null,
  );
  const prepareButton = useRef<HTMLButtonElement>(null);
  const editor = useRef<HTMLElement>(null);
  const focusAfterSave = useRef(false);
  useEffect(() => {
    if (editing) editor.current?.querySelector("input")?.focus();
  }, [editing]);
  const query = useQuery({
    queryKey: practiceKey(itemId),
    queryFn: () => practiceApi.state(itemId),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.preparations.some((prep) =>
        ["PENDING", "RUNNING"].includes(prep.status),
      ) ||
      query.state.data?.rounds?.some((round) => round.status === "GRADING") ||
      query.state.data?.round?.status === "GRADING"
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
    mutationFn: ({
      revision,
      restart,
    }: {
      revision: number;
      restart?: PracticeRound;
    }) => {
      const key = JSON.stringify([
        revision,
        restart?.test_id,
        restart?.version,
      ]);
      if (request.current?.key !== key)
        request.current = { key, id: crypto.randomUUID() };
      return practiceApi.prepare(itemId, revision, request.current.id, restart);
    },
    onSuccess: () => {
      request.current = null;
      return refresh();
    },
  });
  const startRound = useMutation({
    mutationFn: ({
      revision,
      preparationId,
    }: {
      revision: number;
      preparationId: string;
    }) => {
      if (roundRequest.current?.preparationId !== preparationId)
        roundRequest.current = { preparationId, id: crypto.randomUUID() };
      return practiceApi.startRound(
        itemId,
        revision,
        roundRequest.current.id,
        preparationId,
      );
    },
    onSuccess: async (result) => {
      await Promise.all([
        refresh(),
        queryClient.invalidateQueries({
          queryKey: quizTestKeys.detail(result.test_id),
        }),
        ...(query.data?.round && query.data.round.test_id !== result.test_id
          ? [
              queryClient.invalidateQueries({
                queryKey: quizTestKeys.detail(query.data.round.test_id),
              }),
            ]
          : []),
      ]);
      await navigate({
        to: "/plan-items/$itemId/practice",
        params: { itemId },
        search: { round: result.test_id },
        replace: true,
      });
    },
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
    (!state.round || latest?.expected_round_id === state.round.test_id) &&
    state.editable &&
    !state.requirements_stale &&
    req !== null &&
    latest !== undefined &&
    latest.requirements_revision === req.revision &&
    latest.status === "SUCCEEDED" &&
    latest.outcome === "READY";
  const selected =
    state.rounds?.find((round) => round.test_id === selectedRoundId) ??
    state.round;
  return (
    <section className="practice-workspace w-full min-w-0 space-y-6 p-4 pb-24 sm:p-6 sm:pb-24">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          to="/spaces/$courseId"
          params={{ courseId: state.course_id }}
          search={{ tab: "plan" }}
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          <ArrowLeft aria-hidden="true" />
          {t("practice.back")}
        </Link>
        <Button variant="ghost" size="sm" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" />
          {t("practice.refresh")}
        </Button>
      </div>
      <header className="space-y-2">
        <h1 className="text-headline text-ink font-semibold">
          {t("practice.workspace.title")}
        </h1>
        <p className="text-body max-w-reading text-ink-muted wrap-anywhere">
          {state.plan_content}
        </p>
      </header>
      {!state.editable ? (
        <p role="status" className="text-body text-ink-muted">
          {t("practice.recovery.readonly")}
        </p>
      ) : null}
      {state.rounds && state.rounds.length > 1 ? (
        <nav
          aria-label={t("practice.recovery.history")}
          className="flex flex-wrap gap-2"
        >
          {state.rounds.map((round) => (
            <Link
              key={round.test_id}
              to="/plan-items/$itemId/practice"
              params={{ itemId }}
              search={{ round: round.test_id }}
              aria-current={
                selected?.test_id === round.test_id ? "page" : undefined
              }
              className={buttonVariants({
                variant:
                  selected?.test_id === round.test_id ? "secondary" : "ghost",
                size: "sm",
              })}
            >
              {t("practice.round.title", { round: round.round_no })}
              {round.test_id === state.round?.test_id
                ? ` · ${t("practice.recovery.latest")}`
                : ""}
            </Link>
          ))}
        </nav>
      ) : null}
      <div className="practice-layout">
        <div className="min-w-0 space-y-6">
          {selected ? (
            <PracticeRoundCard
              key={selected.test_id}
              round={selected}
              courseId={state.course_id}
              itemId={itemId}
              editable={state.editable}
              primary={!readyToStart}
            />
          ) : null}
          {latest ? (
            <PracticePreparationResult
              latest={latest}
              cancelPending={cancel.isPending}
              onCancel={(id) => cancel.mutate(id)}
            />
          ) : req && !selected ? (
            <div className="bg-surface-raised space-y-3 rounded-xl p-6">
              <h2 className="text-ink text-base font-semibold">
                {t("practice.workspace.readyToPrepare")}
              </h2>
              <p className="text-body text-ink-muted">
                {t("practice.workspace.prepareHint")}
              </p>
            </div>
          ) : null}
          {req && state.editable ? (
            <div className="space-y-3">
              <div className="flex flex-wrap justify-end gap-3">
                <Button
                  ref={prepareButton}
                  variant={state.round || readyToStart ? "outline" : "default"}
                  disabled={
                    active || prepare.isPending || state.requirements_stale
                  }
                  onClick={() =>
                    state.round
                      ? setRestartConfirmation(state.round)
                      : prepare.mutate({ revision: req.revision })
                  }
                >
                  {t(
                    state.round
                      ? "practice.recovery.restart"
                      : latest
                        ? "practice.retry"
                        : "practice.prepare",
                  )}
                </Button>
                {readyToStart ? (
                  <Button
                    disabled={startRound.isPending}
                    onClick={() =>
                      startRound.mutate({
                        revision: req.revision,
                        preparationId: latest.id,
                      })
                    }
                  >
                    {t(
                      state.round
                        ? "practice.recovery.startNext"
                        : "practice.round.start",
                    )}
                    <ArrowRight aria-hidden="true" />
                  </Button>
                ) : null}
              </div>
              <p className="text-label text-ink-muted">
                {t("practice.workspace.safetyHint")}
              </p>
            </div>
          ) : null}
          {state.editable && (!req || editing) ? (
            <section
              ref={editor}
              id="practice-requirements-editor"
              aria-label={t("practice.workspace.editor")}
              className="bg-surface-raised space-y-5 rounded-xl p-4 sm:p-6"
            >
              <h2 className="text-ink text-base font-semibold">
                {t("practice.workspace.editor")}
              </h2>
              {state.round ? (
                <p className="text-body text-ink-muted">
                  {t("practice.recovery.nextRequirements")}
                </p>
              ) : null}
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
            </section>
          ) : null}
          {error ? (
            <p role="alert" className="text-body text-danger">
              {error instanceof ApiError
                ? t(`errors.${error.code}`, {
                    defaultValue: t("practice.failed"),
                  })
                : t("practice.failed")}
            </p>
          ) : null}
        </div>
        <PracticeRequirementsPanel
          state={state}
          editing={editing}
          onEdit={() => setEditing((value) => !value)}
        />
      </div>
      <Dialog
        open={restartConfirmation !== null}
        onOpenChange={(open) => {
          if (!open) setRestartConfirmation(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("practice.recovery.restart")}</DialogTitle>
            <DialogDescription>
              {t(
                restartConfirmation?.status === "IN_PROGRESS"
                  ? "practice.recovery.abandonImpact"
                  : "practice.recovery.restartImpact",
                {
                  answered: restartConfirmation?.answered_count,
                  total: restartConfirmation?.total_count,
                },
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="border-0 bg-transparent">
            <Button
              variant="secondary"
              onClick={() => setRestartConfirmation(null)}
            >
              {t("practice.recovery.cancel")}
            </Button>
            <Button
              onClick={() => {
                if (req && restartConfirmation)
                  prepare.mutate({
                    revision: req.revision,
                    restart: restartConfirmation,
                  });
                setRestartConfirmation(null);
              }}
            >
              {t("practice.recovery.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
