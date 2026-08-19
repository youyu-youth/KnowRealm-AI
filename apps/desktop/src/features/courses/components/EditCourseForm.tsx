import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type { CourseDetail, CourseUpdate } from "@/features/courses/api/types";
import {
  type CourseFormValues,
  type CourseRequiredField,
  courseFieldId,
  courseFormPayloadFromValues,
  courseFormValuesFromCourse,
  invalidCourseFormField,
} from "@/features/courses/courseFormValues";
import { CourseFormFields } from "@/features/courses/components/CourseFormFields";

type EditCourseFormProps = {
  course: CourseDetail;
  onCancel: () => void;
  onSaved: () => void | Promise<void>;
};

function parseHotWords(value: string): string[] {
  return value
    .split("\n")
    .map((word) => word.trim())
    .filter(Boolean);
}

export function EditCourseForm({
  course,
  onCancel,
  onSaved,
}: EditCourseFormProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<CourseFormValues>(() =>
    courseFormValuesFromCourse(course),
  );
  const [fieldError, setFieldError] = useState<{
    field: CourseRequiredField;
    message: string;
  } | null>(null);
  const [hotWordsText, setHotWordsText] = useState(() =>
    (course.hot_words ?? []).join("\n"),
  );
  const [hotWordsError, setHotWordsError] = useState<string | null>(null);
  const updateCourse = useMutation({
    mutationFn: (payload: CourseUpdate) => courseApi.update(course.id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: courseKeys.detail(course.id),
      });
      await queryClient.invalidateQueries({ queryKey: courseKeys.lists() });
      await onSaved();
    },
  });

  function handleChange(patch: Partial<CourseFormValues>) {
    setValues((prev) => ({ ...prev, ...patch }));
    setFieldError(null);
  }

  const fieldErrorMessages: Record<CourseRequiredField, string> = {
    name: t("spaces.editForm.nameRequired"),
    educationStage: t("spaces.editForm.stageRequired"),
    depth: t("spaces.editForm.depthRequired"),
  };

  function rejectInvalid(field: CourseRequiredField, message: string) {
    setFieldError({ field, message });
    document.getElementById(courseFieldId(field))?.focus();
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalidField = invalidCourseFormField(values);
    if (invalidField !== null) {
      rejectInvalid(invalidField, fieldErrorMessages[invalidField]);
      return;
    }
    const hotWords = parseHotWords(hotWordsText);
    if (hotWords.length > 100) {
      setHotWordsError(t("spaces.editForm.hotWordsTooMany"));
      document.getElementById("course-hot-words")?.focus();
      return;
    }
    updateCourse.mutate({
      ...courseFormPayloadFromValues(values),
      hot_words: hotWords,
    });
  }

  const errors: Partial<Record<keyof CourseFormValues, string>> = fieldError
    ? { [fieldError.field]: fieldError.message }
    : {};

  return (
    <form onSubmit={handleSubmit} className="mt-2 flex flex-col gap-5">
      <div>
        <h2 className="text-section font-section text-ink">
          {t("spaces.editForm.title")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground mt-1">
          {t("spaces.editForm.description")}
        </p>
      </div>
      <CourseFormFields
        values={values}
        onChange={handleChange}
        errors={errors}
      />

      <Field data-invalid={hotWordsError ? "true" : undefined}>
        <FieldLabel htmlFor="course-hot-words">
          {t("spaces.editForm.hotWords")}
        </FieldLabel>
        <Textarea
          id="course-hot-words"
          value={hotWordsText}
          onChange={(event) => {
            setHotWordsText(event.target.value);
            setHotWordsError(null);
          }}
          aria-invalid={hotWordsError ? true : undefined}
          aria-describedby="course-hot-words-description"
          className="min-h-28 resize-y"
        />
        <FieldDescription id="course-hot-words-description">
          {t("spaces.editForm.hotWordsDescription", {
            count: parseHotWords(hotWordsText).length,
          })}
        </FieldDescription>
        <FieldError>{hotWordsError}</FieldError>
      </Field>

      {updateCourse.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{updateCourse.error.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={updateCourse.isPending}
        >
          {t("spaces.editForm.cancel")}
        </Button>
        <Button type="submit" disabled={updateCourse.isPending}>
          {updateCourse.isPending ? (
            <Spinner
              data-icon="inline-start"
              aria-label={t("spaces.editForm.saving")}
            />
          ) : null}
          {t("spaces.editForm.submit")}
        </Button>
      </div>
    </form>
  );
}
