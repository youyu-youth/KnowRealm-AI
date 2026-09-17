// 示意数据（假数据先行）：课堂详情的课程级统计、知识图谱、章级掌握、学习上下文、
// 洞察建议、重点推荐与课程对话。后端目前没有课程级聚合 / 掌握度 / 知识点接口，
// 对应统计与掌握度域接入后整体替换本模块；UI 以「示意」标签明示。
// 数值基于课程 id 确定性生成：同一课程跨组件一致，且不随重渲染跳动。

import type { CourseDetail } from "@/features/courses/api/types";

export type MasteryState = "mastered" | "learning" | "untouched";

export type CourseCoreStats = {
  /** 课程章节数（示意） */
  chapters: number;
  /** 知识点个数（示意） */
  knowledgePoints: number;
  /** 习题集个数（示意） */
  quizSets: number;
};

export type ChapterMastery = {
  id: string;
  /** 1 起的章节序号 */
  index: number;
  /** 章节名 i18n key（示意名称） */
  nameKey: string;
  percent: number;
  state: MasteryState;
};

export type RecommendedPoint = {
  id: string;
  titleKey: string;
  chapter: number;
  section: string;
  /** 示意学习人数（千），显示为 12.4k */
  learnersK: number;
};

export type InsightSuggestion = {
  key: "nextChapter" | "hotWords" | "focusReview";
  count?: number;
  chapter?: ChapterMastery;
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

export function masteryStateOf(percent: number): MasteryState {
  if (percent >= 80) return "mastered";
  if (percent > 0) return "learning";
  return "untouched";
}

/** 供封面等纯装饰元素复用的稳定种子。 */
export function courseDetailSeed(courseId: string): number {
  return hash(courseId);
}

export function mockCourseCoreStats(courseId: string): CourseCoreStats {
  const seed = hash(courseId);
  return {
    chapters: 6 + (seed % 5),
    knowledgePoints: 120 + ((seed >>> 6) % 260),
    quizSets: 24 + ((seed >>> 13) % 40),
  };
}

const CHAPTER_NAME_COUNT = 8;

export function mockChapterMastery(course: CourseDetail): ChapterMastery[] {
  const seed = hash(`${course.id}-chapters`);
  const count = mockCourseCoreStats(course.id).chapters;
  return Array.from({ length: count }, (_, index) => {
    const percent = Math.max(0, 88 - index * 11 - ((seed >>> (index * 2)) % 9));
    return {
      id: `${course.id}-chapter-${index + 1}`,
      index: index + 1,
      nameKey: `spaces.courseDetail.mock.chapters.${index % CHAPTER_NAME_COUNT}`,
      percent,
      state: masteryStateOf(percent),
    };
  });
}

/** 当前进度 = 第一个未掌握章节；全部掌握时取最后一章。 */
export function mockCurrentProgress(course: CourseDetail): ChapterMastery {
  const chapters = mockChapterMastery(course);
  return (
    chapters.find((chapter) => chapter.state !== "mastered") ??
    chapters[chapters.length - 1]
  );
}

const SUBJECT_COUNT = 6;

export function mockSubjectKey(course: CourseDetail): string {
  return `spaces.courseDetail.mock.subjects.${hash(`${course.id}-subject`) % SUBJECT_COUNT}`;
}

export function mockInsightSuggestions(
  course: CourseDetail,
): InsightSuggestion[] {
  const seed = hash(`${course.id}-insights`);
  const progress = mockCurrentProgress(course);
  const all: InsightSuggestion[] = [
    { key: "nextChapter", chapter: progress },
    { key: "hotWords", count: Math.max(1, (course.hot_words ?? []).length) },
    { key: "focusReview", count: 3 + (seed % 6), chapter: progress },
  ];
  const start = seed % all.length;
  return [0, 1, 2].map((offset) => all[(start + offset) % all.length]);
}

const POINT_TITLE_COUNT = 9;

/** 重点推荐：按 batch 轮转，每次 3 条（示意）。 */
export function mockRecommendedPoints(
  course: CourseDetail,
  batch: number,
): RecommendedPoint[] {
  const seed = hash(`${course.id}-points`);
  return Array.from({ length: 3 }, (_, offset) => {
    const poolIndex = (seed + batch * 3 + offset) % POINT_TITLE_COUNT;
    return {
      id: `${course.id}-point-${poolIndex}`,
      titleKey: `spaces.courseDetail.mock.points.${poolIndex}`,
      chapter: (poolIndex % 8) + 1,
      section: `${(poolIndex % 8) + 1}.${(poolIndex % 5) + 1}`,
      learnersK: (8 + ((seed >>> (poolIndex % 16)) % 120)) / 10,
    };
  });
}
