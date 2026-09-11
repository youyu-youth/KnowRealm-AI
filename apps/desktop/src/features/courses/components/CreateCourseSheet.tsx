import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  type CourseFormValues,
  courseFormPayloadFromValues,
  emptyCourseFormValues,
  invalidCourseFormField,
  presetLearningContext,
} from "@/features/courses/courseFormValues";
import { CourseFormFields } from "@/features/courses/components/CourseFormFields";
import { settingsKeys } from "@/features/settings/api/keys";
import { profileApi } from "@/features/settings/api/profile";

type CreateCourseSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CreateCourseSheet({
  open,
  onOpenChange,
}: CreateCourseSheetProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<CourseFormValues>(emptyCourseFormValues);
  const profile = useQuery({
    queryKey: settingsKeys.profile,
    queryFn: () => profileApi.get(),
  });
  const createCourse = useMutation({
    mutationFn: courseApi.create,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: courseKeys.lists() });
      resetForm();
      onOpenChange(false);
    },
  });

  // 学习场景初值随档案派生（可改）：用户未选定（空）且抽屉打开时取角色预选；
  // 用户一旦选定即以用户值为准——档案晚到不覆盖选择，也不抹掉其它已输入字段。
  const presetContext = presetLearningContext(
    profile.data?.primary_role ?? null,
  );
  const formValues: CourseFormValues =
    open && values.learningContext === ""
      ? { ...values, learningContext: presetContext }
      : values;

  const canSubmit = invalidCourseFormField(formValues) === null;

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
    createCourse.mutate(courseFormPayloadFromValues(formValues));
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className="sm:max-w-md" showCloseButton={false}>
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <SheetHeader>
            <SheetTitle>{t("spaces.form.title")}</SheetTitle>
            <SheetDescription>{t("spaces.form.description")}</SheetDescription>
          </SheetHeader>

          <SheetBody>
            <CourseFormFields
              values={formValues}
              onChange={(patch) => setValues((prev) => ({ ...prev, ...patch }))}
              showInitialStatus
            />

            {createCourse.isError ? (
              <Alert variant="destructive" className="mt-4">
                <AlertDescription>
                  {createCourse.error.message}
                </AlertDescription>
              </Alert>
            ) : null}
          </SheetBody>

          <SheetFooter>
            <SheetClose
              render={<Button variant="outline" type="button" />}
              disabled={createCourse.isPending}
            >
              {t("spaces.form.cancel")}
            </SheetClose>
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
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
