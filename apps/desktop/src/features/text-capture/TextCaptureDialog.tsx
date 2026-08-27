import { useMutation, useQuery } from "@tanstack/react-query";
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
import { Textarea } from "@/components/ui/textarea";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  textCaptureApi,
  type TextCaptureAccepted,
  type TextCaptureMode,
} from "@/features/text-capture/api/textCaptures";

const MAX_TEXT_BYTES = 1024 * 1024;

type TextCaptureDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  captureType: TextCaptureMode;
  onAccepted: (result: TextCaptureAccepted, courseSelected: boolean) => void;
};

export function TextCaptureDialog({
  open,
  onOpenChange,
  captureType,
  onAccepted,
}: TextCaptureDialogProps) {
  const { t } = useTranslation();
  const [content, setContent] = useState("");
  const [courseId, setCourseId] = useState<string | null>(null);
  const showCourse = captureType === "PASTE";
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open && showCourse,
  });
  const activeCourses = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const byteLength = new TextEncoder().encode(content).length;
  const oversized = byteLength > MAX_TEXT_BYTES;
  const canSubmit = content.trim().length > 0 && !oversized;

  const submitCapture = useMutation({
    mutationFn: () =>
      textCaptureApi.create({
        capture_type: captureType,
        content,
        ...(showCourse ? { course_id: courseId } : {}),
      }),
    onSuccess: async (result) => {
      const courseSelected = showCourse && courseId !== null;
      resetForm();
      onOpenChange(false);
      await onAccepted(result, courseSelected);
    },
  });

  function resetForm() {
    setContent("");
    setCourseId(null);
    submitCapture.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (submitCapture.isPending) return;
    if (!nextOpen) resetForm();
    onOpenChange(nextOpen);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || submitCapture.isPending) return;
    submitCapture.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>
              {t(
                captureType === "QUICK_NOTE"
                  ? "textCapture.quickNoteTitle"
                  : "textCapture.pasteTitle",
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                captureType === "QUICK_NOTE"
                  ? "textCapture.quickNoteDescription"
                  : "textCapture.pasteDescription",
              )}
            </DialogDescription>
          </DialogHeader>

          <Field>
            <FieldLabel htmlFor="text-capture-body">
              {t("textCapture.body")}
            </FieldLabel>
            <Textarea
              id="text-capture-body"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={10}
              autoFocus
              // field-sizing-content 会让超长单行粘贴把 Dialog 撑宽、撑高，恢复固定尺寸后在框内滚动。
              className="field-sizing-fixed"
              aria-required="true"
              aria-describedby="text-capture-body-hint"
            />
            <p
              id="text-capture-body-hint"
              className="text-label text-muted-foreground"
            >
              {t("textCapture.bodyHint")}
            </p>
            {oversized ? (
              <FieldDescription>
                {t("textCapture.sizeExceeded")}
              </FieldDescription>
            ) : null}
          </Field>

          {showCourse ? (
            <Field>
              <FieldLabel htmlFor="text-capture-course">
                {t("textCapture.course")}
              </FieldLabel>
              <Select
                items={[
                  { value: "__none__", label: t("textCapture.noCourse") },
                  ...activeCourses.map((course) => ({
                    value: course.id,
                    label: course.name,
                  })),
                ]}
                value={courseId}
                onValueChange={(value) =>
                  setCourseId(value === "__none__" ? null : value)
                }
                disabled={courses.isPending}
              >
                <SelectTrigger id="text-capture-course" className="w-full">
                  <SelectValue placeholder={t("textCapture.coursePlaceholder")}>
                    {courseId
                      ? (activeCourses.find((course) => course.id === courseId)
                          ?.name ?? null)
                      : t("textCapture.noCourse")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="__none__">
                      {t("textCapture.noCourse")}
                    </SelectItem>
                    {activeCourses.map((course) => (
                      <SelectItem key={course.id} value={course.id}>
                        {course.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {courses.isError ? (
                <FieldDescription>
                  {t("textCapture.courseError")}
                </FieldDescription>
              ) : (
                <FieldDescription>
                  {t("textCapture.courseHint")}
                </FieldDescription>
              )}
            </Field>
          ) : null}

          {submitCapture.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{submitCapture.error.message}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <DialogClose
              render={
                <Button variant="outline" disabled={submitCapture.isPending} />
              }
            >
              {t("textCapture.cancel")}
            </DialogClose>
            <Button
              type="submit"
              disabled={!canSubmit || submitCapture.isPending}
            >
              {submitCapture.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("textCapture.submitting")}
                />
              ) : null}
              {t("textCapture.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
