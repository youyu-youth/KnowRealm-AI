import { useTranslation } from "react-i18next";

import { appToast } from "@/components/common/appToastManager";
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
import { useArchiveConcept } from "@/features/courses/api/courseBrain";
import type { BrainConcept } from "@/features/courses/api/types";

type CourseBrainArchiveDialogProps = {
  courseId: string;
  concept: BrainConcept | null;
  onOpenChange: (open: boolean) => void;
  /** 归档成功后回调（详情面板关闭）。 */
  onArchived: () => void;
};

/** 概念归档二次确认：CONFIRMED→ARCHIVED 受控退役，成功后关闭详情面板。 */
export function CourseBrainArchiveDialog({
  courseId,
  concept,
  onOpenChange,
  onArchived,
}: CourseBrainArchiveDialogProps) {
  const { t } = useTranslation();
  const archiveConcept = useArchiveConcept(courseId);

  function handleOpenChange(nextOpen: boolean) {
    if (archiveConcept.isPending) return;
    if (!nextOpen) archiveConcept.reset();
    onOpenChange(nextOpen);
  }

  function handleArchive() {
    if (!concept) return;
    archiveConcept.mutate(concept.id, {
      onSuccess: () => {
        appToast.add({
          description: t("spaces.courseDetail.brain.archive.success", {
            name: concept.canonical_name,
          }),
        });
        archiveConcept.reset();
        onArchived();
      },
    });
  }

  return (
    <Dialog open={concept !== null} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>
            {t("spaces.courseDetail.brain.archive.title")}
          </DialogTitle>
          <DialogDescription>
            {t("spaces.courseDetail.brain.archive.description", {
              name: concept?.canonical_name ?? "",
            })}
          </DialogDescription>
        </DialogHeader>

        {archiveConcept.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{archiveConcept.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("spaces.courseDetail.brain.archive.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            onClick={handleArchive}
            disabled={archiveConcept.isPending}
          >
            {archiveConcept.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("spaces.courseDetail.brain.archive.archiving")}
              />
            ) : null}
            {t("spaces.courseDetail.brain.archive.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
