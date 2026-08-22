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
import {
  audioImportApi,
  type AudioImportAccepted,
} from "@/features/audio-import/api/audioImports";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  documentImportApi,
  type DocumentImportAccepted,
} from "@/features/document-import/api/documentImports";
import { recordKeys } from "@/features/records/api/keys";

type ImportAccepted = DocumentImportAccepted | AudioImportAccepted;
type ImportVariables = {
  selectedCourseId: string | null;
  selectedFile: File;
  audio: boolean;
};

type DocumentImportDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccepted: (result: ImportAccepted) => void | Promise<void>;
};

const audioExtensions = [".mp3", ".aac", ".wav", ".m4a"];

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
  const isAudio = file
    ? audioExtensions.some((extension) =>
        file.name.toLocaleLowerCase().endsWith(extension),
      )
    : false;
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open,
  });
  const activeCourses = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const courseItems = [
    ...(isAudio
      ? [{ value: "__none__", label: t("documentImport.noCourse") }]
      : []),
    ...activeCourses.map((course) => ({
      value: course.id,
      label: course.name,
    })),
  ];
  const importDocument = useMutation<ImportAccepted, Error, ImportVariables>({
    mutationFn: ({ selectedCourseId, selectedFile, audio }: ImportVariables) =>
      audio
        ? audioImportApi.create(selectedCourseId, selectedFile)
        : documentImportApi.create(selectedCourseId ?? "", selectedFile),
    onSuccess: async (result, variables) => {
      if (variables.selectedCourseId) {
        await queryClient.invalidateQueries({
          queryKey: recordKeys.courseList(variables.selectedCourseId),
        });
      }
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
    if (!file || (!isAudio && !courseId)) return;
    importDocument.mutate({
      selectedCourseId: courseId,
      selectedFile: file,
      audio: isAudio,
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
              <SelectTrigger
                id="document-import-course"
                className="w-full"
                aria-required={!isAudio}
              >
                <SelectValue
                  placeholder={t("documentImport.coursePlaceholder")}
                >
                  {courseId
                    ? (activeCourses.find((course) => course.id === courseId)
                        ?.name ?? null)
                    : isAudio
                      ? t("documentImport.noCourse")
                      : null}
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
            {courses.isError ||
            (!isAudio && !courses.isPending && activeCourses.length === 0) ? (
              <FieldDescription>
                {courses.isError
                  ? t("documentImport.courseError")
                  : t("documentImport.noActiveCourse")}
              </FieldDescription>
            ) : isAudio ? (
              <FieldDescription>
                {t("documentImport.audioCourseHint")}
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
              accept=".txt,.md,.pdf,.docx,.mp3,.aac,.wav,.m4a"
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
              disabled={
                !file || (!isAudio && !courseId) || importDocument.isPending
              }
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
