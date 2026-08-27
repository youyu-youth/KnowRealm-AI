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
  captureBatchApi,
  type CaptureBatchAccepted,
} from "@/features/document-import/api/captureBatches";
import { recordKeys } from "@/features/records/api/keys";

type ImportVariables = {
  selectedCourseId: string | null;
  selectedFiles: File[];
};

type DocumentImportDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccepted: (result: CaptureBatchAccepted) => void | Promise<void>;
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
  const [files, setFiles] = useState<File[]>([]);
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open,
  });
  const activeCourses = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const courseItems = [
    { value: "__none__", label: t("documentImport.noCourse") },
    ...activeCourses.map((course) => ({
      value: course.id,
      label: course.name,
    })),
  ];
  const importDocument = useMutation<
    CaptureBatchAccepted,
    Error,
    ImportVariables
  >({
    mutationFn: ({ selectedCourseId, selectedFiles }) =>
      captureBatchApi.create(selectedCourseId, selectedFiles),
    onSuccess: async (result, variables) => {
      if (variables.selectedCourseId) {
        await queryClient.invalidateQueries({
          queryKey: recordKeys.courseList(variables.selectedCourseId),
        });
      } else {
        await queryClient.invalidateQueries({ queryKey: recordKeys.inbox() });
      }
      resetForm();
      onOpenChange(false);
      await onAccepted(result);
    },
  });

  function resetForm() {
    setCourseId(null);
    setFiles([]);
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
    if (files.length === 0) return;
    importDocument.mutate({
      selectedCourseId: courseId,
      selectedFiles: files,
    });
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
              onValueChange={(value) =>
                setCourseId(value === "__none__" ? null : value)
              }
              disabled={courses.isPending || courseItems.length === 0}
            >
              <SelectTrigger id="document-import-course" className="w-full">
                <SelectValue
                  placeholder={t("documentImport.coursePlaceholder")}
                >
                  {courseId
                    ? (activeCourses.find((course) => course.id === courseId)
                        ?.name ?? null)
                    : t("documentImport.noCourse")}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {courseItems.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            {courses.isError ? (
              <FieldDescription>
                {t("documentImport.courseError")}
              </FieldDescription>
            ) : (
              <FieldDescription>
                {t("documentImport.audioCourseHint")}
              </FieldDescription>
            )}
          </Field>

          <Field>
            <FieldLabel htmlFor="document-import-file">
              {t("documentImport.file")}
            </FieldLabel>
            <Input
              ref={fileInput}
              id="document-import-file"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx,.mp3,.aac,.wav,.m4a"
              aria-required="true"
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []))
              }
            />
            <FieldDescription>{t("documentImport.fileHint")}</FieldDescription>
            {files.length > 0 ? (
              <ol className="border-border max-h-32 min-w-0 divide-y overflow-y-auto border-y">
                {files.map((selectedFile, index) => (
                  <li
                    key={`${selectedFile.name}-${selectedFile.size}-${index}`}
                    className="text-body text-ink flex min-w-0 gap-3 py-2"
                  >
                    <span className="text-label text-muted-foreground shrink-0 tabular-nums">
                      {index + 1}
                    </span>
                    <span
                      className="min-w-0 truncate"
                      title={selectedFile.name}
                    >
                      {selectedFile.name}
                    </span>
                  </li>
                ))}
              </ol>
            ) : null}
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
              disabled={files.length === 0 || importDocument.isPending}
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
