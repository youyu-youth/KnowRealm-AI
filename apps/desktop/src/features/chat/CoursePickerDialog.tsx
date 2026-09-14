import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { GraduationCap } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { courseKeys } from "@/features/courses/api/keys";
import { courseApi } from "@/features/courses/api/courses";

type CoursePickerDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 选定课程（未作废；确认按钮触发）；pending 期间禁用确认。 */
  onConfirm: (courseId: string) => void;
  pending?: boolean;
  error?: string | null;
};

/** 选课 Dialog（复用课程列表数据）：范围胶囊「课程」与新建菜单「课程问答」共用。 */
export function CoursePickerDialog({
  open,
  onOpenChange,
  onConfirm,
  pending = false,
  error = null,
}: CoursePickerDialogProps) {
  const { t } = useTranslation();
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open,
    staleTime: 0,
  });
  const items = courses.data ?? [];

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (pending) return;
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("chat.coursePicker.title")}</DialogTitle>
          <DialogDescription>
            {t("chat.coursePicker.description")}
          </DialogDescription>
        </DialogHeader>
        {courses.isPending ? (
          <p
            role="status"
            className="text-label text-muted-foreground flex items-center gap-2"
          >
            <Spinner aria-hidden="true" className="size-3" />
            {t("chat.coursePicker.loading")}
          </p>
        ) : courses.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{t("chat.coursePicker.error")}</AlertDescription>
            <Button variant="outline" onClick={() => void courses.refetch()}>
              {t("chat.retry")}
            </Button>
          </Alert>
        ) : items.length === 0 ? (
          <p className="text-body text-muted-foreground">
            {t("chat.coursePicker.empty")}
          </p>
        ) : (
          <ul
            aria-label={t("chat.coursePicker.title")}
            className="flex max-h-72 flex-col gap-1 overflow-y-auto"
          >
            {items.map((course) => (
              <li key={course.id}>
                <button
                  type="button"
                  className="hover:bg-surface-subtle focus-visible:ring-ring/40 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-start transition-colors focus-visible:ring-3"
                  disabled={pending}
                  onClick={() => onConfirm(course.id)}
                >
                  <span className="bg-surface-subtle flex size-8 shrink-0 items-center justify-center rounded-md">
                    <GraduationCap
                      className="text-ink-muted size-4"
                      aria-hidden="true"
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="text-body text-ink block truncate font-medium">
                      {course.name}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" disabled={pending} />}>
            {t("chat.rename.cancel")}
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
