import type { TFunction } from "i18next";

// 统计带时长两档格式：不足 1 小时「X 分钟」，≥1 小时「X 小时 Y 分」（整小时省分钟）。
// 数值与小号文本（单位词）分开返回，单位由调用方按「小号内联浅色」降级渲染。
export type DurationPart = { text: string; muted: boolean };

export function formatLearningDurationParts(
  durationMs: number,
  t: TFunction,
): DurationPart[] {
  const totalMinutes = Math.round(durationMs / 60_000);
  if (totalMinutes < 60) {
    return [
      { text: String(totalMinutes), muted: false },
      { text: t("today.stats.duration.minutesUnit"), muted: true },
    ];
  }
  const hours = Math.floor(totalMinutes / 60);
  const restMinutes = totalMinutes % 60;
  const parts: DurationPart[] = [
    { text: String(hours), muted: false },
    { text: t("today.stats.duration.hoursUnit"), muted: true },
  ];
  if (restMinutes > 0) {
    parts.push(
      { text: String(restMinutes), muted: false },
      { text: t("today.stats.duration.minutesShortUnit"), muted: true },
    );
  }
  return parts;
}

export function formatLearningDurationText(
  durationMs: number,
  t: TFunction,
): string {
  return formatLearningDurationParts(durationMs, t)
    .map((part) => part.text)
    .join(" ");
}
