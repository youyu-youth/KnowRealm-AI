import { useMemo, useRef, type ComponentProps } from "react";
import { CalendarDays, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import type { TodayPlanItem } from "@/features/today/api/today";
import { TodayPlanFilters } from "@/features/today/components/TodayPlanFilters";
import { TodayPlanTask } from "@/features/today/components/TodayPlanTask";

type Props = {
  items: TodayPlanItem[];
  allItems: TodayPlanItem[];
  selectedItemId?: string;
  busyItemId?: string;
  isCompleting: boolean;
  error: boolean;
  onRetry: () => void;
  onFocus: (id: string) => void;
  onComplete: (item: TodayPlanItem) => void;
  finalFocus: ComponentProps<typeof DialogContent>["finalFocus"];
};

export function TodayPlanItemsDialog({
  items,
  allItems,
  selectedItemId,
  busyItemId,
  isCompleting,
  error,
  onRetry,
  onFocus,
  onComplete,
  finalFocus,
}: Props) {
  const { t } = useTranslation();
  const title = useRef<HTMLHeadingElement>(null);
  const courses = useMemo(
    () =>
      Array.from(
        new Map(
          allItems.map((item) => [
            item.course_id,
            { course_id: item.course_id, course_name: item.course_name },
          ]),
        ).values(),
      ),
    [allItems],
  );
  return (
    <DialogContent
      className="today-workspace today-plan-dialog"
      showCloseButton={false}
      initialFocus={title}
      finalFocus={finalFocus}
    >
      <header className="today-plan-dialog-header">
        <div className="min-w-0">
          <DialogTitle
            ref={title}
            tabIndex={-1}
            className="today-plan-dialog-title"
          >
            <CalendarDays className="size-6 shrink-0" aria-hidden="true" />
            {t("today.planDialog.title")}
          </DialogTitle>
          <DialogDescription className="text-label mt-2">
            {t("today.planDialog.count", { count: items.length })}
          </DialogDescription>
        </div>
        <DialogClose
          render={<Button size="icon-sm" variant="ghost" />}
          aria-label={t("today.planDialog.close")}
        >
          <X aria-hidden="true" />
        </DialogClose>
      </header>
      <div className="today-plan-dialog-filters">
        <TodayPlanFilters courses={courses} />
      </div>
      <div className="today-plan-dialog-body">
        {error ? (
          <div role="alert" className="p-6">
            <p className="text-body text-destructive">
              {t("today.errorTitle")}
            </p>
            <Button className="mt-3" variant="outline" onClick={onRetry}>
              {t("today.retry")}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <p role="status" className="text-body text-ink-muted p-6">
            {t("today.workspace.noTasks")}
          </p>
        ) : (
          <ul
            className="today-plan-card-grid"
            aria-label={t("today.planDialog.list")}
          >
            {items.map((item) => (
              <li
                key={item.item_id}
                className="min-w-0"
                aria-busy={busyItemId === item.item_id}
              >
                <TodayPlanTask
                  expanded
                  item={item}
                  selected={selectedItemId === item.item_id}
                  busy={busyItemId === item.item_id}
                  disabled={isCompleting}
                  onFocus={onFocus}
                  onComplete={onComplete}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </DialogContent>
  );
}
