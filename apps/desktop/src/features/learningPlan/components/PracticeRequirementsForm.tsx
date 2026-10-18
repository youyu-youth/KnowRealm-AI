import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  practiceApi,
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

export function PracticeRequirementsForm({
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
      <div className="grid gap-5 sm:grid-cols-3">
        <label className="text-body block space-y-2 sm:col-span-2">
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
      </div>
      <fieldset className="space-y-2">
        <legend className="text-body mb-2 font-medium">
          {t("practice.types")}
        </legend>
        <div className="flex flex-wrap gap-3">
          {TYPES.map((type) => (
            <label
              key={type}
              className="text-body bg-surface-subtle has-checked:bg-surface-strong flex cursor-pointer items-center gap-2 rounded-md px-3 py-2"
            >
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
        <legend className="text-body mb-2 font-medium">
          {t("practice.sources")}
        </legend>
        {sources.map((source) => (
          <label
            key={source.record_id}
            className="text-body bg-surface-subtle has-checked:bg-surface-strong flex cursor-pointer items-start gap-3 rounded-md p-3"
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
              <span className="text-label text-ink-muted mt-1 block">
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
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          className="h-auto min-h-9 whitespace-normal"
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
        <Button
          type="submit"
          className="h-auto min-h-9 whitespace-normal"
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
      </div>
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
    </form>
  );
}
