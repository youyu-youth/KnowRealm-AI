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
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type { CourseDetail } from "@/features/courses/api/types";

type DeleteCourseDialogProps = {
  course: CourseDetail;
  onDeleted: () => void | Promise<void>;
};

export function DeleteCourseDialog({
  course,
  onDeleted,
}: DeleteCourseDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const deleteCourse = useMutation({
    mutationFn: () => courseApi.delete(course.id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: courseKeys.detail(course.id),
          exact: true,
          refetchType: "none",
        }),
        queryClient.invalidateQueries({ queryKey: courseKeys.lists() }),
      ]);
      setOpen(false);
      await onDeleted();
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteCourse.isPending) return;
    if (!nextOpen) deleteCourse.reset();
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button variant="destructive" />}>
        {t("spaces.delete.action")}
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("spaces.delete.title")}</DialogTitle>
          <DialogDescription>
            {t("spaces.delete.description", { name: course.name })}
          </DialogDescription>
        </DialogHeader>

        {deleteCourse.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{deleteCourse.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("spaces.delete.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            onClick={() => deleteCourse.mutate()}
            disabled={deleteCourse.isPending}
          >
            {deleteCourse.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("spaces.delete.deleting")}
              />
            ) : null}
            {t("spaces.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
