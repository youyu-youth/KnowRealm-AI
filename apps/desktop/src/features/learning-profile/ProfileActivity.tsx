import { useQuery } from "@tanstack/react-query";
import { Clock3 } from "lucide-react";
import { DayButton } from "react-day-picker";
import { enUS, zhCN } from "react-day-picker/locale";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { ProfileActivityHeatmap } from "@/features/learning-profile/ProfileActivityHeatmap";
import { todayApi } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { localDateKey } from "@/features/learning-profile/profileSearch";
import { cn } from "@/lib/utils";

export function ProfileActivity({
  date,
  onDateChange,
}: {
  date?: string;
  onDateChange: (date: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const today = new Date();
  const selected = date ?? localDateKey(today);
  const [view, setView] = useState(() => ({
    selection: selected,
    month: new Date(`${selected.slice(0, 7)}-01T12:00:00`),
  }));
  const month =
    view.selection === selected
      ? view.month
      : new Date(`${selected.slice(0, 7)}-01T12:00:00`);
  const setMonth = (month: Date) => setView({ selection: selected, month });
  const trend = useQuery({
    queryKey: todayKeys.trend(30),
    queryFn: () => todayApi.trend(30),
  });
  const points = new Map(
    trend.data?.map((point) => [point.date, point.total_ms]),
  );
  const selectedMs = points.get(selected);
  const dates = [...points.keys()].sort();
  const withinRange =
    dates.length > 0 &&
    selected >= dates[0] &&
    selected <= dates[dates.length - 1];
  const format = (value: Date, options: Intl.DateTimeFormatOptions) =>
    value.toLocaleDateString(i18n.resolvedLanguage, options);
  return (
    <aside
      id="profile-calendar"
      className="profile-activity border-border-subtle bg-surface-subtle/40 min-w-0 border-r p-5"
    >
      <Calendar
        className="profile-month-calendar w-full bg-transparent p-0"
        mode="single"
        required
        fixedWeeks
        weekStartsOn={1}
        locale={i18n.resolvedLanguage?.startsWith("zh") ? zhCN : enUS}
        month={month}
        onMonthChange={setMonth}
        selected={new Date(`${selected}T12:00:00`)}
        onSelect={(day) => {
          onDateChange(localDateKey(day));
          setMonth(new Date(day.getFullYear(), day.getMonth(), 1, 12));
        }}
        labels={{
          labelPrevious: () => t("learningProfile.calendar.previous"),
          labelNext: () => t("learningProfile.calendar.next"),
          labelDayButton: (day) =>
            format(day, { year: "numeric", month: "long", day: "numeric" }),
        }}
        formatters={{
          formatCaption: (value) =>
            format(value, { year: "numeric", month: "long" }),
        }}
        components={{
          DayButton,
          CaptionLabel: ({ children, ...props }) => (
            <span {...props}>
              {children}
              <span
                className="text-profile-month font-course-display text-ink-strong mt-4 block leading-none tabular-nums"
                aria-hidden="true"
              >
                {String(month.getMonth() + 1).padStart(2, "0")}
              </span>
            </span>
          ),
        }}
        classNames={{
          day_button: cn(
            buttonVariants({ variant: "ghost", size: "icon" }),
            "aspect-square h-full w-full rounded-full p-0 font-normal",
          ),
          month_caption: "flex min-h-30 w-full items-start pr-16",
          caption_label: "text-body text-ink pt-1",
          nav: "absolute right-0 top-0 flex gap-1",
        }}
      />
      <section
        className="border-border-subtle mt-5 border-t pt-4"
        aria-labelledby="profile-activity-title"
      >
        <h2
          id="profile-activity-title"
          className="text-body font-section text-ink"
        >
          {t("learningProfile.calendar.activity")}
        </h2>
        <p className="text-label text-ink-muted mt-1">
          {t("learningProfile.calendar.scope")}
        </p>
        {trend.isPending ? (
          <p role="status" className="text-label text-ink-muted mt-4">
            {t("learningProfile.loading")}
          </p>
        ) : trend.isError ? (
          <div className="mt-3">
            <p role="alert" className="text-label text-destructive">
              {t("learningProfile.calendar.error")}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => void trend.refetch()}
            >
              {t("learningProfile.retry")}
            </Button>
          </div>
        ) : (
          <ProfileActivityHeatmap
            points={trend.data}
            selected={selected}
            onSelect={(day) => {
              onDateChange(day);
              setMonth(new Date(`${day.slice(0, 7)}-01T12:00:00`));
            }}
          />
        )}
      </section>
      <section className="bg-paper mt-5 rounded-sm p-3" aria-live="polite">
        <h2 className="text-body font-section text-ink">
          {format(new Date(`${selected}T12:00:00`), {
            month: "long",
            day: "numeric",
            weekday: "short",
          })}
        </h2>
        <p className="text-label text-ink-muted mt-4 flex items-center gap-2">
          <Clock3 className="size-4 shrink-0" aria-hidden="true" />
          {t("learningProfile.calendar.duration")}
        </p>
        <p className="text-body text-ink mt-2 tabular-nums">
          {trend.isPending || trend.isError
            ? "—"
            : selectedMs === undefined
              ? t(
                  withinRange
                    ? "learningProfile.calendar.unavailable"
                    : "learningProfile.calendar.outside",
                )
              : t("learningProfile.calendar.minutes", {
                  count: Math.round(selectedMs / 60000),
                })}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3"
          onClick={() => {
            onDateChange(localDateKey(today));
            setMonth(new Date(today.getFullYear(), today.getMonth(), 1, 12));
          }}
        >
          {t("learningProfile.calendar.today")}
        </Button>
      </section>
    </aside>
  );
}
