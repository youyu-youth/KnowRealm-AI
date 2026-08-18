import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  type CourseFormValues,
  courseFormPayloadFromValues,
  emptyCourseFormValues,
  invalidCourseFormField,
} from "@/features/courses/courseFormValues";
import { CourseFormFields } from "@/features/courses/components/CourseFormFields";

type CreateCourseDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CreateCourseDialog({
  open,
  onOpenChange,
}: CreateCourseDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<CourseFormValues>(emptyCourseFormValues);
  const createCourse = useMutation({
    mutationFn: courseApi.create,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: courseKeys.lists() });
      resetForm();
      onOpenChange(false);
    },
  });

  const canSubmit = invalidCourseFormField(values) === null;

  function resetForm() {
    setValues(emptyCourseFormValues);
    createCourse.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && !createCourse.isPending) resetForm();
    onOpenChange(nextOpen);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    createCourse.mutate(courseFormPayloadFromValues(values));
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{t("spaces.form.title")}</DialogTitle>
            <DialogDescription>
              {t("spaces.form.description")}
            </DialogDescription>
          </DialogHeader>

          <CourseFormFields
            values={values}
            onChange={(patch) => setValues((prev) => ({ ...prev, ...patch }))}
          />

          {createCourse.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{createCourse.error.message}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              {t("spaces.form.cancel")}
            </DialogClose>
            <Button
              type="submit"
              disabled={!canSubmit || createCourse.isPending}
            >
              {createCourse.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("spaces.form.saving")}
                />
              ) : null}
              {t("spaces.form.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
