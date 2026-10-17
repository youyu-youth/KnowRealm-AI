import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useRecordStudy } from "@/features/learningPlan/api/study";
import { useUpdatePlanItem } from "@/features/learningPlan/api/learningPlan";

export function StudySourcePicker({
  itemId,
  courseId,
  planId,
  onSaved,
}: {
  itemId: string;
  courseId: string;
  planId: string;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const study = useRecordStudy(itemId, q);
  const update = useUpdatePlanItem(courseId);
  const selectedVisible = study.data?.sources.some(
    (source) => source.record_id === selected,
  );
  return (
    <form
      className="border-border-subtle grid gap-3 rounded-md border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!selected || !selectedVisible) return;
        update.mutate(
          { planId, itemId, body: { record_id: selected } },
          { onSuccess: onSaved },
        );
      }}
    >
      <h2 className="text-section font-section">{t("study.chooseSource")}</h2>
      <Input
        aria-label={t("study.searchSource")}
        placeholder={t("study.searchSource")}
        value={q}
        onChange={(event) => {
          setQ(event.target.value);
          setSelected(null);
        }}
      />
      {study.isPending ? (
        <p role="status">{t("learningPlan.loading")}</p>
      ) : null}
      {study.data?.sources_truncated ? <p>{t("study.truncated")}</p> : null}
      <RadioGroup
        aria-label={t("study.chooseSource")}
        value={selected ?? ""}
        onValueChange={setSelected}
      >
        {study.data?.sources.map((source) => (
          <label
            key={source.record_id}
            className="flex min-w-0 items-center gap-2 py-1"
          >
            <RadioGroupItem value={source.record_id} />
            <span className="min-w-0 break-words">
              {source.title}
              {source.read_only ? ` · ${t("study.sharedReadonly")}` : ""}
            </span>
          </label>
        ))}
      </RadioGroup>
      {study.data?.sources.length === 0 ? <p>{t("study.noSources")}</p> : null}
      <Button
        className="justify-self-start"
        type="submit"
        disabled={!selectedVisible || update.isPending || study.isFetching}
      >
        {t("study.confirmSource")}
      </Button>
      {study.error || update.error ? (
        <p role="alert" className="text-destructive">
          {(study.error ?? update.error)?.message}
        </p>
      ) : null}
      {study.isError ? (
        <Button variant="outline" onClick={() => void study.refetch()}>
          {t("learningPlan.retry")}
        </Button>
      ) : null}
    </form>
  );
}
