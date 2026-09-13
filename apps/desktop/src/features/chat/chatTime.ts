import type { TFunction } from "i18next";

function isSameDay(left: Date, right: Date): boolean {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

/** 会话时间戳：今天/昨天带“今天”字样，更早显示月日与时分。 */
export function formatChatTimestamp(
  t: TFunction,
  locale: string,
  iso: string,
): string {
  const date = new Date(iso);
  const now = new Date();
  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  if (isSameDay(date, now)) {
    return t("chat.time.todayAt", { time });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (isSameDay(date, yesterday)) {
    return t("chat.time.yesterdayAt", { time });
  }
  return new Intl.DateTimeFormat(locale, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
