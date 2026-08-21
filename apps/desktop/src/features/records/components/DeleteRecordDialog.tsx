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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { documentImportKeys } from "@/features/document-import/api/keys";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";

type DeleteRecordDialogProps = {
  recordId: string;
  courseId: string;
  title: string;
  jobId?: string;
  onDeletingChange: (deleting: boolean) => void;
  onDeleted: (courseId: string) => void | Promise<void>;
};

export function DeleteRecordDialog({
  recordId,
  courseId,
  title,
  jobId,
  onDeletingChange,
  onDeleted,
}: DeleteRecordDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const deleteRecord = useMutation({
    mutationFn: () => recordApi.delete(recordId),
    onMutate: () => onDeletingChange(true),
    onError: () => onDeletingChange(false),
    onSuccess: async () => {
      if (jobId) {
        await queryClient.cancelQueries({
          queryKey: documentImportKeys.job(jobId),
          exact: true,
        });
      }
      await queryClient.invalidateQueries({
        queryKey: recordKeys.courseList(courseId),
        exact: true,
        refetchType: "none",
      });
      queryClient.removeQueries({
        queryKey: recordKeys.detail(recordId),
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: recordKeys.transcript(recordId),
        exact: true,
      });
      if (jobId) {
        queryClient.removeQueries({
          queryKey: documentImportKeys.job(jobId),
          exact: true,
        });
      }
      setOpen(false);
      await onDeleted(courseId);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteRecord.isPending) return;
    if (!nextOpen) deleteRecord.reset();
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button variant="destructive" />}>
        {t("record.delete.action")}
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("record.delete.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("record.delete.description", { title })}
          </DialogDescription>
        </DialogHeader>

        {deleteRecord.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{deleteRecord.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("record.delete.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            onClick={() => deleteRecord.mutate()}
            disabled={deleteRecord.isPending}
          >
            {deleteRecord.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("record.delete.deleting")}
              />
            ) : null}
            {t("record.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
