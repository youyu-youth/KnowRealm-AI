// 示意数据（假数据先行）：知识空间统计、课程卡片统计、最近活跃、待归类与最近活动。
// 后端目前没有课程级聚合接口（知识点总数 / 记录总数 / 学习进度 / 周活跃），
// 对应统计域接入后整体替换本模块；UI 以「示意」标签明示，不与真实数据混排。
// 数值基于课程 id 确定性生成：同一课程在卡片、统计与活动区始终一致，且不随重渲染跳动。

import type { Course } from "@/features/courses/api/types";

export type SpacesCourseStats = {
  /** 学习记录条数 */
  records: number;
  /** 知识点个数 */
  knowledgePoints: number;
  /** 学习进度百分比（0–100） */
  progress: number;
};

export type SpacesCourseInsight = {
  course: Course;
  stats: SpacesCourseStats;
  /** 最近活跃距今的天数（0 = 今天） */
  lastActiveDaysAgo: number;
  lastActiveHour: number;
  lastActiveMinute: number;
  activityKind: "records" | "knowledgePoints";
  activityAmount: number;
};

export type SpacesOverview = {
  courseCount: number;
  recordCount: number;
  knowledgePointCount: number;
  activeThisWeek: number;
};

export type SpacesPendingItemKey =
  "notes" | "knowledgePoints" | "documents" | "recordings";

export type SpacesPendingItem = {
  key: SpacesPendingItemKey;
  count: number;
};

export type SpacesActivity = {
  id: string;
  course: Course;
  daysAgo: number;
  hour: number;
  minute: number;
  kind: "records" | "knowledgePoints" | "progress";
  amount: number;
};

/** FNV-1a 32 位哈希：仅用于生成稳定的示意数值。 */
function hash(value: string): number {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return result >>> 0;
}

export function mockCourseStats(courseId: string): SpacesCourseStats {
  const seed = hash(courseId);
  return {
    records: 18 + (seed % 88),
    knowledgePoints: 40 + ((seed >>> 8) % 360),
    progress: 18 + ((seed >>> 16) % 73),
  };
}

function mockCourseInsight(course: Course): SpacesCourseInsight {
  const seed = hash(course.id);
  return {
    course,
    stats: mockCourseStats(course.id),
    lastActiveDaysAgo: (seed >>> 4) % 14,
    lastActiveHour: 8 + ((seed >>> 12) % 13),
    lastActiveMinute: (seed >>> 20) % 60,
    activityKind: seed % 3 === 0 ? "knowledgePoints" : "records",
    activityAmount: 1 + (seed % 5),
  };
}

export function mockSpacesOverview(courses: Course[]): SpacesOverview {
  const insights = courses.map(mockCourseInsight);
  return {
    courseCount: courses.length,
    recordCount: insights.reduce(
      (total, insight) => total + insight.stats.records,
      0,
    ),
    knowledgePointCount: insights.reduce(
      (total, insight) => total + insight.stats.knowledgePoints,
      0,
    ),
    activeThisWeek: insights.filter((insight) => insight.lastActiveDaysAgo < 7)
      .length,
  };
}

/** 最近活跃课程：按示意活跃时间排序，取前若干门真实课程。 */
export function mockRecentCourses(
  courses: Course[],
  limit = 4,
): SpacesCourseInsight[] {
  return courses
    .map(mockCourseInsight)
    .sort((left, right) => left.lastActiveDaysAgo - right.lastActiveDaysAgo)
    .slice(0, limit);
}

export const mockPendingItems: SpacesPendingItem[] = [
  { key: "notes", count: 12 },
  { key: "knowledgePoints", count: 8 },
  { key: "documents", count: 5 },
  { key: "recordings", count: 3 },
];

/** 最近活动：真实课程名 + 示意时间与增量。 */
export function mockActivities(courses: Course[], limit = 5): SpacesActivity[] {
  return mockRecentCourses(courses, limit).map((insight, index) => ({
    id: `${insight.course.id}-${index}`,
    course: insight.course,
    daysAgo: insight.lastActiveDaysAgo,
    hour: insight.lastActiveHour,
    minute: insight.lastActiveMinute,
    kind:
      insight.activityKind === "records" && insight.activityAmount % 2 === 0
        ? "progress"
        : insight.activityKind,
    amount: insight.activityAmount,
  }));
}
