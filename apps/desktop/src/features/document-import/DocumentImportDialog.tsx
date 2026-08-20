import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  documentImportApi,
  type DocumentImportAccepted,
} from "@/features/document-import/api/documentImports";
import { recordKeys } from "@/features/records/api/keys";

type DocumentImportDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccepted: (result: DocumentImportAccepted) => void | Promise<void>;
};

export function DocumentImportDialog({
  open,
  onOpenChange,
  onAccepted,
}: DocumentImportDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open,
  });
  const activeCourses = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const courseItems = activeCourses.map((course) => ({
    value: course.id,
    label: course.name,
  }));
  const importDocument = useMutation({
    mutationFn: ({
      selectedCourseId,
      selectedFile,
    }: {
      selectedCourseId: string;
      selectedFile: File;
    }) => documentImportApi.create(selectedCourseId, selectedFile),
    onSuccess: async (result, variables) => {
      await queryClient.invalidateQueries({
        queryKey: recordKeys.courseList(variables.selectedCourseId),
      });
      resetForm();
      onOpenChange(false);
      await onAccepted(result);
    },
  });

  function resetForm() {
    setCourseId(null);
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
    importDocument.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (importDocument.isPending) return;
    if (!nextOpen) resetForm();
    onOpenChange(nextOpen);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!courseId || !file) return;
    importDocument.mutate({ selectedCourseId: courseId, selectedFile: file });
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{t("documentImport.title")}</DialogTitle>
            <DialogDescription>
              {t("documentImport.description")}
            </DialogDescription>
          </DialogHeader>

          <Field>
            <FieldLabel htmlFor="document-import-course">
              {t("documentImport.course")}
            </FieldLabel>
            <Select
              items={courseItems}
              value={courseId}
              onValueChange={setCourseId}
              disabled={courses.isPending || courseItems.length === 0}
            >
              <SelectTrigger
                id="document-import-course"
                className="w-full"
                aria-required="true"
              >
                <SelectValue
                  placeholder={t("documentImport.coursePlaceholder")}
                >
                  {activeCourses.find((course) => course.id === courseId)
                    ?.name ?? null}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {activeCourses.map((course) => (
                    <SelectItem key={course.id} value={course.id}>
                      {course.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            {courses.isError ||
            (!courses.isPending && activeCourses.length === 0) ? (
              <FieldDescription>
                {courses.isError
                  ? t("documentImport.courseError")
                  : t("documentImport.noActiveCourse")}
              </FieldDescription>
            ) : null}
          </Field>

          <Field>
            <FieldLabel htmlFor="document-import-file">
              {t("documentImport.file")}
            </FieldLabel>
            <Input
              ref={fileInput}
              id="document-import-file"
              type="file"
              accept=".txt,.md,.pdf,.docx"
              aria-required="true"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <FieldDescription>{t("documentImport.fileHint")}</FieldDescription>
          </Field>

          {importDocument.isError ? (
            <Alert variant="destructive">
              <AlertDescription>
                {importDocument.error.message}
              </AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <DialogClose
              render={
                <Button variant="outline" disabled={importDocument.isPending} />
              }
            >
              {t("documentImport.cancel")}
            </DialogClose>
            <Button
              type="submit"
              disabled={!courseId || !file || importDocument.isPending}
            >
              {importDocument.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("documentImport.submitting")}
                />
              ) : null}
              {t("documentImport.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
