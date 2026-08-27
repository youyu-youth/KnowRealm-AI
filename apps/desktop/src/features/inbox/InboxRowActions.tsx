import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, FolderInput } from "lucide-react";
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
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import { useActiveCourses } from "@/features/courses/api/queries";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordOut } from "@/features/records/api/types";

const ORGANIZABLE_STATUSES = new Set(["NOTE", "SUMMARY_PENDING"]);

export function InboxRowActions({
  record,
  onClassified,
}: {
  record: RecordOut;
  onClassified: (courseName: string) => void;
}) {
  if (!ORGANIZABLE_STATUSES.has(record.status)) return null;
  return (
    <>
      <InboxClassifyButton record={record} onClassified={onClassified} />
      <InboxUpgradeButton record={record} />
    </>
  );
}

function InboxClassifyButton({
  record,
  onClassified,
}: {
  record: RecordOut;
  onClassified: (courseName: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [courseId, setCourseId] = useState<string | null>(null);
  const { courses } = useActiveCourses(open);
  const title = record.title.trim() || t("spaces.records.untitled");

  const classify = useMutation({
    mutationFn: (selectedCourseId: string) =>
      recordApi.classify(record.id, selectedCourseId),
    onSuccess: async (_result, selectedCourseId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: recordKeys.inbox() }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.courseList(selectedCourseId),
        }),
      ]);
      setOpen(false);
      onClassified(
        courses.find((course) => course.id === selectedCourseId)?.name ?? "",
      );
      setCourseId(null);
      classify.reset();
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (classify.isPending) return;
    if (!nextOpen) {
      classify.reset();
      setCourseId(null);
    }
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("inbox.classify.action", { title })}
          />
        }
      >
        <FolderInput aria-hidden="true" />
        {t("inbox.classify.short")}
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("inbox.classify.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("inbox.classify.description", { title })}
          </DialogDescription>
        </DialogHeader>
        <ActiveCourseSelect
          id="inbox-classify-course"
          value={courseId}
          onValueChange={setCourseId}
          disabled={classify.isPending}
        />
        {classify.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{classify.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("inbox.classify.cancel")}
          </DialogClose>
          <Button
            disabled={courseId === null || classify.isPending}
            onClick={() => {
              if (courseId !== null) classify.mutate(courseId);
            }}
          >
            {classify.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("inbox.classify.submitting")}
              />
            ) : null}
            {t("inbox.classify.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InboxUpgradeButton({ record }: { record: RecordOut }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [courseId, setCourseId] = useState<string | null>(null);
  const title = record.title.trim() || t("spaces.records.untitled");

  const upgrade = useMutation({
    mutationFn: (selectedCourseId: string) =>
      recordApi.upgrade(record.id, selectedCourseId),
    onSuccess: async (_result, selectedCourseId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: recordKeys.inbox() }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.detail(record.id),
        }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.summary(record.id),
        }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.courseList(selectedCourseId),
        }),
      ]);
      setOpen(false);
      void navigate({
        to: "/records/$recordId",
        params: { recordId: record.id },
      });
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (upgrade.isPending) return;
    if (!nextOpen) {
      upgrade.reset();
      setCourseId(null);
    }
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("inbox.upgrade.action", { title })}
          />
        }
      >
        <ArrowUpRight aria-hidden="true" />
        {t("inbox.upgrade.short")}
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("inbox.upgrade.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("inbox.upgrade.description", { title })}
          </DialogDescription>
        </DialogHeader>
        <ActiveCourseSelect
          id="inbox-upgrade-course"
          value={courseId}
          onValueChange={setCourseId}
          disabled={upgrade.isPending}
        />
        {upgrade.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{upgrade.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("inbox.upgrade.cancel")}
          </DialogClose>
          <Button
            disabled={courseId === null || upgrade.isPending}
            onClick={() => {
              if (courseId !== null) upgrade.mutate(courseId);
            }}
          >
            {upgrade.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("inbox.upgrade.submitting")}
              />
            ) : null}
            {t("inbox.upgrade.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
