// 课程列表时间按 DESIGN.md 规则展示：今天 HH:mm，昨天「昨天 HH:mm」，更早为本地化日期。

const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dayFormatters = new Map<string, Intl.DateTimeFormat>();

function dayFormatter(locale: string): Intl.DateTimeFormat {
  let formatter = dayFormatters.get(locale);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
    });
    dayFormatters.set(locale, formatter);
  }
  return formatter;
}

function dayStart(value: Date): number {
  return new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate(),
  ).getTime();
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * 将 ISO 时间格式化为列表时间：今天只显示时刻；昨天带「昨天」前缀；更早显示月日。
 * `yesterdayTemplate` 为 i18n 模板（含 {{time}} 占位符）。
 */
export function formatCourseMoment(
  value: string | Date,
  yesterdayTemplate: string,
  locale: string,
): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const dayDiff = Math.round((dayStart(new Date()) - dayStart(date)) / DAY_MS);
  if (dayDiff <= 0) return timeFormatter.format(date);
  if (dayDiff === 1)
    return yesterdayTemplate.replace("{{time}}", timeFormatter.format(date));
  return dayFormatter(locale).format(date);
}
