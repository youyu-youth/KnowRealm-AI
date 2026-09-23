import { useMutation, useQueryClient } from "@tanstack/react-query";
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

type ArchiveCourseDialogProps = {
  course: { id: string; name: string };
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** 课程归档二次确认（工单 03）：状态翻转保留全部数据；成功后留在当前页面
 * （状态标签即时更新），失败内联呈现（如已归档 409）。 */
export function ArchiveCourseDialog({
  course,
  open,
  onOpenChange,
}: ArchiveCourseDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const archiveCourse = useMutation({
    mutationFn: () => courseApi.archive(course.id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: courseKeys.detail(course.id),
          exact: true,
          refetchType: "none",
        }),
        queryClient.invalidateQueries({ queryKey: courseKeys.lists() }),
      ]);
      onOpenChange(false);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (archiveCourse.isPending) return;
    if (!nextOpen) archiveCourse.reset();
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("spaces.archive.title")}</DialogTitle>
          <DialogDescription>
            {t("spaces.archive.description", { name: course.name })}
          </DialogDescription>
        </DialogHeader>

        {archiveCourse.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{archiveCourse.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("spaces.archive.cancel")}
          </DialogClose>
          <Button
            onClick={() => archiveCourse.mutate()}
            disabled={archiveCourse.isPending}
          >
            {archiveCourse.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("spaces.archive.archiving")}
              />
            ) : null}
            {t("spaces.archive.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
