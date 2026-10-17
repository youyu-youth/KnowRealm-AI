import { PracticePreparationResult } from "@/features/learningPlan/components/PracticePreparationResult";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  practiceApi,
  practiceKey,
  type PracticeState,
  type QuestionType,
} from "@/features/learningPlan/api/practice";
import { ApiError } from "@/services/http/client";

const TYPES: QuestionType[] = [
  "MULTIPLE_CHOICE",
  "MULTIPLE_SELECT",
  "TRUE_FALSE",
  "FILL_BLANK",
  "SHORT_ANSWER",
];

function RequirementsForm({
  state,
  saved,
  reload,
}: {
  state: PracticeState;
  saved: () => void;
  reload: () => Promise<PracticeState | undefined>;
}) {
  const { t } = useTranslation();
  const req = state.requirements;
  const [sources, setSources] = useState(state.sources);
  const [reloaded, setReloaded] = useState(false);
  const [baseline, setBaseline] = useState({
    revision: req?.revision ?? 0,
    planContent: state.plan_content,
  });
  const [topic, setTopic] = useState(req?.topic ?? state.plan_content);
  // 数量必须由用户明确确认，旧计划文字不自动推断数量。
  const [count, setCount] = useState(req ? String(req.question_count) : "");
  const [types, setTypes] = useState<QuestionType[]>(
    req?.question_types ?? TYPES,
  );
  const [records, setRecords] = useState<string[]>(req?.record_ids ?? []);
  const save = useMutation({
    mutationFn: () =>
      practiceApi.confirm(state.item_id, {
        expected_revision: baseline.revision,
        plan_content: baseline.planContent,
        topic,
        question_count: Number(count),
        question_types: types,
        record_ids: records,
        source_versions: Object.fromEntries(
          sources
            .filter((source) => records.includes(source.record_id))
            .map((source) => [source.record_id, source.version]),
        ),
      }),
    onSuccess: saved,
  });
  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <label className="text-body block space-y-2">
        <span>{t("practice.topic")}</span>
        <Input
          required
          maxLength={200}
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
        />
      </label>
      <label className="text-body block space-y-2">
        <span>{t("practice.count")}</span>
        <Input
          required
          type="number"
          min={1}
          step={1}
          value={count}
          onChange={(event) => setCount(event.target.value)}
        />
      </label>
      <fieldset className="space-y-2">
        <legend className="text-body mb-2">{t("practice.types")}</legend>
        <div className="flex flex-wrap gap-4">
          {TYPES.map((type) => (
            <label key={type} className="text-body flex items-center gap-2">
              <Checkbox
                checked={types.includes(type)}
                onCheckedChange={(checked) =>
                  setTypes((current) =>
                    checked
                      ? [...current, type]
                      : current.filter((value) => value !== type),
                  )
                }
              />
              {t(`practice.type.${type}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="space-y-3">
        <legend className="text-body mb-2">{t("practice.sources")}</legend>
        {sources.map((source) => (
          <label
            key={source.record_id}
            className="text-body flex items-start gap-2"
          >
            <Checkbox
              checked={records.includes(source.record_id)}
              onCheckedChange={(checked) =>
                setRecords((current) =>
                  checked
                    ? [...current, source.record_id]
                    : current.filter((value) => value !== source.record_id),
                )
              }
            />
            <span className="min-w-0 wrap-anywhere">
              {source.title}{" "}
              <span className="text-ink-muted">
                {t("practice.inventory", { count: source.eligible_count })}
              </span>
            </span>
          </label>
        ))}
        {records
          .filter((id) => !sources.some((source) => source.record_id === id))
          .map((id) => (
            <label key={id} className="text-body flex items-start gap-2">
              <Checkbox
                checked
                onCheckedChange={() =>
                  setRecords((current) =>
                    current.filter((value) => value !== id),
                  )
                }
              />
              <span className="min-w-0 wrap-anywhere">
                {t("practice.sourceUnavailable")} · {id}
              </span>
            </label>
          ))}
      </fieldset>
      <p className="text-label text-ink-muted">{t("practice.confirmHint")}</p>
      <Button
        type="button"
        variant="outline"
        onClick={() =>
          void reload().then((current) => {
            if (current) {
              setSources(current.sources);
              setBaseline({
                revision: current.requirements?.revision ?? 0,
                planContent: current.plan_content,
              });
              setReloaded(true);
            }
          })
        }
      >
        {t("practice.reloadSources")}
      </Button>
      {reloaded ? (
        <p role="status" className="text-label text-ink-muted">
          {t("practice.sourcesReloaded")}
        </p>
      ) : null}
      {save.error ? (
        <p role="alert" className="text-body text-danger">
          {save.error instanceof ApiError
            ? t(`errors.${save.error.code}`, {
                defaultValue: t("practice.failed"),
              })
            : t("practice.failed")}
        </p>
      ) : null}
      <Button
        type="submit"
        disabled={
          save.isPending ||
          !topic.trim() ||
          !Number.isSafeInteger(Number(count)) ||
          Number(count) < 1 ||
          !types.length ||
          !records.length
        }
      >
        {t("practice.confirm")}
      </Button>
    </form>
  );
}

export function PracticePreparationPage({ itemId }: { itemId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const request = useRef<{ revision: number; id: string } | null>(null);
  const prepareButton = useRef<HTMLButtonElement>(null);
  const focusAfterSave = useRef(false);
  const query = useQuery({
    queryKey: practiceKey(itemId),
    queryFn: () => practiceApi.state(itemId),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.preparations.some((prep) =>
        ["PENDING", "RUNNING"].includes(prep.status),
      )
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
  const error = prepare.error ?? cancel.error;
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
        <RequirementsForm
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
