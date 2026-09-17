import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import {
  courseBrainApi,
  BRAIN_PAGE_LIMIT,
} from "@/features/courses/api/courseBrain";
import { courseBrainKeys } from "@/features/courses/api/keys";
import { recordApi } from "@/features/records/api/records";

type BrainConcept = components["schemas"]["BrainConceptOut"];

type QuizConceptFieldProps = {
  recordId: string;
  quizId: string;
  /** 记录未关联课程时无概念可选，组件整体隐藏 */
  courseId: string | null;
  conceptId?: string | null;
  conceptName?: string | null;
  /** 可编辑 = 首次作答前；作答后为只读归属展示 */
  editable: boolean;
  onUpdated: (concept: {
    conceptId: string | null;
    conceptName: string | null;
  }) => void;
};

export function QuizConceptField({
  recordId,
  quizId,
  courseId,
  conceptId,
  conceptName,
  editable,
  onUpdated,
}: QuizConceptFieldProps) {
  const { t } = useTranslation();
  const boundId = conceptId ?? null;
  const boundName = conceptName ?? null;
  const concepts = useQuery({
    queryKey: courseBrainKeys.concepts(courseId ?? "", {
      status: "CONFIRMED",
      limit: BRAIN_PAGE_LIMIT,
    }),
    queryFn: () =>
      courseBrainApi.concepts(courseId ?? "", {
        status: "CONFIRMED",
        limit: BRAIN_PAGE_LIMIT,
      }),
    enabled: editable && courseId != null,
  });
  const setConcept = useMutation({
    mutationFn: (nextConceptId: string | null) =>
      recordApi.setQuizConcept(recordId, quizId, { concept_id: nextConceptId }),
    onSuccess: (updated) =>
      onUpdated({
        conceptId: updated.concept_id ?? null,
        conceptName: updated.concept_name ?? null,
      }),
  });

  if (!editable) {
    return (
      <p className="text-label text-muted-foreground mt-3">
        {t("record.detail.quiz.concept.readonly", {
          name: boundName ?? t("record.detail.quiz.concept.none"),
        })}
      </p>
    );
  }
  if (courseId == null) {
    return null;
  }

  const options: BrainConcept[] = concepts.data ?? [];
  const pick = (nextId: string | null) => {
    if (nextId === boundId || setConcept.isPending) {
      return;
    }
    setConcept.mutate(nextId);
  };

  return (
    <Field className="mt-4 gap-1.5">
      <FieldLabel htmlFor={`quiz-concept-${quizId}`}>
        {t("record.detail.quiz.concept.label")}
      </FieldLabel>
      <div className="flex items-center gap-2">
        <Select
          items={options.map((concept) => ({
            value: concept.id,
            label: concept.canonical_name,
          }))}
          value={boundId}
          onValueChange={(value) => pick(value)}
          disabled={
            concepts.isPending || setConcept.isPending || options.length === 0
          }
        >
          <SelectTrigger
            id={`quiz-concept-${quizId}`}
            aria-label={t("record.detail.quiz.concept.label")}
            className="w-64"
          >
            <SelectValue
              placeholder={t("record.detail.quiz.concept.placeholder")}
            >
              {options.find((concept) => concept.id === boundId)
                ?.canonical_name ?? null}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {options.map((concept) => (
                <SelectItem key={concept.id} value={concept.id}>
                  {concept.canonical_name}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        {boundId != null ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={setConcept.isPending}
            onClick={() => pick(null)}
          >
            {t("record.detail.quiz.concept.clear")}
          </Button>
        ) : null}
        {setConcept.isPending ? <Spinner aria-hidden="true" /> : null}
      </div>
      <FieldDescription>
        {concepts.isError
          ? t("record.detail.quiz.concept.loadError")
          : options.length === 0
            ? t("record.detail.quiz.concept.emptyCourse")
            : t("record.detail.quiz.concept.lockedHint")}
      </FieldDescription>
      {setConcept.isError ? (
        <p role="alert" className="text-label text-destructive">
          {setConcept.error.message}
        </p>
      ) : null}
    </Field>
  );
}
