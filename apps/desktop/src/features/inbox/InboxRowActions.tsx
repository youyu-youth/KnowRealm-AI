import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, FolderInput, Trash2 } from "lucide-react";
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
  compact = false,
  disabled = false,
}: {
  record: RecordOut;
  onClassified: (courseName: string) => void;
  compact?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-1">
      {ORGANIZABLE_STATUSES.has(record.status) ? (
        <>
          <InboxClassifyButton
            record={record}
            onClassified={onClassified}
            compact={compact}
            disabled={disabled}
          />
          <InboxUpgradeButton
            record={record}
            compact={compact}
            disabled={disabled}
          />
        </>
      ) : null}
      <InboxDeleteButton
        recordId={record.id}
        title={record.title.trim() || undefined}
        compact={compact}
        disabled={disabled}
      />
    </div>
  );
}

function InboxClassifyButton({
  record,
  onClassified,
  compact,
  disabled,
}: {
  record: RecordOut;
  onClassified: (courseName: string) => void;
  compact: boolean;
  disabled: boolean;
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
            size={compact ? "icon" : "sm"}
            aria-label={t("inbox.classify.action", { title })}
            disabled={disabled}
          />
        }
      >
        <FolderInput aria-hidden="true" />
        <span className={compact ? "sr-only" : undefined}>
          {t("inbox.classify.short")}
        </span>
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

function InboxUpgradeButton({
  record,
  compact,
  disabled,
}: {
  record: RecordOut;
  compact: boolean;
  disabled: boolean;
}) {
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
            size={compact ? "icon" : "sm"}
            aria-label={t("inbox.upgrade.action", { title })}
            disabled={disabled}
          />
        }
      >
        <ArrowUpRight aria-hidden="true" />
        <span className={compact ? "sr-only" : undefined}>
          {t("inbox.upgrade.short")}
        </span>
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

function InboxDeleteButton({
  recordId,
  title,
  compact,
  disabled,
}: {
  recordId: string;
  title?: string;
  compact: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const displayTitle = title || t("spaces.records.untitled");
  const deleteRecord = useMutation({
    mutationFn: () => recordApi.delete(recordId),
    onSuccess: async () => {
      queryClient.removeQueries({
        queryKey: recordKeys.detail(recordId),
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: recordKeys.transcript(recordId),
        exact: true,
      });
      await queryClient.invalidateQueries({ queryKey: recordKeys.inbox() });
      setOpen(false);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteRecord.isPending) return;
    if (!nextOpen) deleteRecord.reset();
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size={compact ? "icon" : "sm"}
            aria-label={t("inbox.delete.action", { title: displayTitle })}
            disabled={disabled}
          />
        }
      >
        <Trash2 aria-hidden="true" />
        <span className={compact ? "sr-only" : undefined}>
          {t("inbox.delete.confirm")}
        </span>
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("inbox.delete.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("inbox.delete.description", { title: displayTitle })}
          </DialogDescription>
        </DialogHeader>
        {deleteRecord.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{deleteRecord.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("inbox.delete.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            onClick={() => deleteRecord.mutate()}
            disabled={deleteRecord.isPending}
          >
            {deleteRecord.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("inbox.delete.deleting")}
              />
            ) : null}
            {t("inbox.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
