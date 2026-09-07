// 示意数据（假数据先行）：学习专注度 / 学习进步趋势 / 学科能力雷达 / 学习时间分布
// 目前无对应真数据域（学习画像域未建），对应域接入后整体替换本模块；
// UI 以「示意」标签明示，不与真实统计混排。

export type MockNamedValue = { nameKey: string };

/** 一天内每小时专注分钟数（0:00–24:00 共 25 个刻度）。 */
export const focusByHourMinutes: number[] = [
  10, 5, 0, 0, 0, 0, 15, 40, 80, 110, 90, 70, 95, 120, 100, 60, 75, 110, 140,
  160, 130, 80, 45, 20, 5,
];

export function focusHourLabels(): string[] {
  return Array.from({ length: 25 }, (_, hour) => `${hour}:00`);
}

/** 进步趋势三系列的 30 天日增量；用确定性公式生成，避免手写 90 个数。 */
export const progressDayCount = 30;

function progressValues(
  start: number,
  growth: number,
  amplitude: number,
  phase: number,
): number[] {
  return Array.from({ length: progressDayCount }, (_, i) =>
    Math.max(
      0,
      Math.round(start + i * growth + Math.sin(i / 3 + phase) * amplitude),
    ),
  );
}

export const progressSeries: { nameKey: string; values: number[] }[] = [
  {
    nameKey: "today.stats.insights.series.knowledgePoints",
    values: progressValues(4, 0.35, 2, 0),
  },
  {
    nameKey: "today.stats.insights.series.reviewAccuracy",
    values: progressValues(3, 0.3, 1.5, 1.2),
  },
  {
    nameKey: "today.stats.insights.series.ability",
    values: progressValues(2, 0.25, 1.5, 2.4),
  },
];

/** 与趋势图同源的「最近 N 天」ISO 日期序列（末日 = 今天，UTC）。 */
export function lastNDates(days: number): string[] {
  const today = new Date();
  return Array.from({ length: days }, (_, index) => {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - (days - 1 - index));
    return day.toISOString().slice(0, 10);
  });
}

export type MockRadarIndicator = MockNamedValue & { max: number };

export const radarIndicators: MockRadarIndicator[] = [
  { nameKey: "today.stats.insights.subjects.math", max: 100 },
  { nameKey: "today.stats.insights.subjects.linearAlgebra", max: 100 },
  { nameKey: "today.stats.insights.subjects.dataStructure", max: 100 },
  { nameKey: "today.stats.insights.subjects.probability", max: 100 },
  { nameKey: "today.stats.insights.subjects.english", max: 100 },
  { nameKey: "today.stats.insights.subjects.csBasics", max: 100 },
];

export const radarThisWeek: number[] = [85, 72, 68, 76, 62, 70];
export const radarLastWeek: number[] = [78, 65, 60, 70, 58, 64];

export type MockSlice = MockNamedValue & { percent: number };

export const distributionSlices: MockSlice[] = [
  { nameKey: "today.stats.insights.subjects.math", percent: 36 },
  { nameKey: "today.stats.insights.subjects.linearAlgebra", percent: 24 },
  { nameKey: "today.stats.insights.subjects.dataStructure", percent: 18 },
  { nameKey: "today.stats.insights.subjects.probability", percent: 12 },
  { nameKey: "today.stats.insights.subjects.english", percent: 6 },
  { nameKey: "today.stats.insights.subjects.other", percent: 4 },
];

/** 分布中心的名义总时长（示意数据内部自洽，不读真实统计）。 */
export const distributionTotalHours = 28.6;
