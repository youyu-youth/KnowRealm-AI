// 示意数据（假数据先行）：课堂详情的课程级统计、知识图谱、章级掌握、学习上下文、
// 洞察建议、重点推荐与课程对话。后端目前没有课程级聚合 / 掌握度 / 知识点接口，
// 对应统计与掌握度域接入后整体替换本模块；UI 以「示意」标签明示。
// 数值基于课程 id 确定性生成：同一课程跨组件一致，且不随重渲染跳动。

import type { TFunction } from "i18next";
import type { CourseDetail } from "@/features/courses/api/types";

export type MasteryState = "mastered" | "learning" | "untouched";

export type CourseCoreStats = {
  /** 课程章节数（示意） */
  chapters: number;
  /** 知识点个数（示意） */
  knowledgePoints: number;
  /** 习题集个数（示意） */
  quizSets: number;
  /** 我的掌握度百分比（示意，0–100） */
  masteryPercent: number;
};

export type KnowledgeNode = {
  id: string;
  /** 展示名称：真实热词原样显示，示意名称走 i18n key。 */
  name: string;
  /** true = 来自课程真实热词；false = 示意名称（name 为 i18n key）。 */
  fromHotWords: boolean;
  /** 中心课程节点 */
  core: boolean;
  state: MasteryState;
  /** 相对坐标系（200 × 160）中的确定性位置，供力导视图使用。 */
  x: number;
  y: number;
};

export type MockCourseKnowledgePoint = {
  id: string;
  recordId: string;
  /** 展示名称：课程热词原样显示，示意名称走 i18n key。 */
  name: string;
  fromHotWords: boolean;
  tags: string[];
  importance: number;
};

export type AggregatedCourseKnowledgePoint = {
  id: string;
  name: string;
  fromHotWords: boolean;
  tags: string[];
  totalWeight: number;
  recordCount: number;
  conceptCount: number;
  other: boolean;
};

export type CourseKnowledgeRelation = {
  source: string;
  target: string;
  sharedTagCount: number;
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
  key: "mastery" | "nextChapter" | "hotWords" | "focusReview";
  percent?: number;
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

/** 示意名称的展示文案：热词原样返回，示意名称走 i18n。 */
export function translateNodeName(
  t: TFunction,
  node: Pick<KnowledgeNode, "name" | "fromHotWords">,
): string {
  return node.fromHotWords ? node.name : t(node.name);
}

export function mockCourseCoreStats(courseId: string): CourseCoreStats {
  const seed = hash(courseId);
  return {
    chapters: 6 + (seed % 5),
    knowledgePoints: 120 + ((seed >>> 6) % 260),
    quizSets: 24 + ((seed >>> 13) % 40),
    masteryPercent: 42 + ((seed >>> 19) % 46),
  };
}

const NODE_NAME_COUNT = 14;
const SATELLITE_ANGLES = [-90, -45, 0, 45, 90, 135, 180, 225];

/** 模拟多条学习记录中的知识点；同一名称会跨记录重复，供课程级聚合使用。 */
export function mockCourseKnowledgePoints(
  course: CourseDetail,
): MockCourseKnowledgePoint[] {
  const hotWords = [
    ...new Set((course.hot_words ?? []).map((word) => word.trim())),
  ]
    .filter(Boolean)
    .slice(0, NODE_NAME_COUNT);
  const names = Array.from({ length: NODE_NAME_COUNT }, (_, index) => ({
    name:
      hotWords[index] ??
      `spaces.courseDetail.mock.nodes.${index % NODE_NAME_COUNT}`,
    fromHotWords: index < hotWords.length,
  }));
  const recordCount = 6 + (hash(`${course.id}-knowledge-records`) % 3);

  return Array.from({ length: recordCount }, (_, recordIndex) =>
    Array.from({ length: 4 }, (_, offset) => {
      const nameIndex = (recordIndex * 4 + offset) % names.length;
      const name = names[nameIndex];
      return {
        id: `${course.id}-record-${recordIndex + 1}-point-${offset + 1}`,
        recordId: `${course.id}-record-${recordIndex + 1}`,
        ...name,
        tags: [`cluster-${nameIndex % 4}`, `theme-${(nameIndex + 1) % 3}`],
        importance:
          1 + (hash(`${course.id}-${recordIndex}-${nameIndex}-importance`) % 5),
      };
    }),
  ).flat();
}

/** 同名知识点合并权重，保留 Top N，其余汇总为「其他」。 */
export function aggregateCourseKnowledgePoints(
  points: MockCourseKnowledgePoint[],
  limit = 12,
): AggregatedCourseKnowledgePoint[] {
  const aggregated = new Map<
    string,
    Omit<AggregatedCourseKnowledgePoint, "recordCount"> & {
      recordIds: Set<string>;
    }
  >();

  for (const point of points) {
    const key = point.name.trim().toLocaleLowerCase();
    const current = aggregated.get(key);
    if (current) {
      current.totalWeight += point.importance;
      current.recordIds.add(point.recordId);
      for (const tag of point.tags) {
        if (!current.tags.includes(tag)) current.tags.push(tag);
      }
      continue;
    }
    aggregated.set(key, {
      id: point.id,
      name: point.name,
      fromHotWords: point.fromHotWords,
      tags: [...point.tags],
      totalWeight: point.importance,
      recordIds: new Set([point.recordId]),
      conceptCount: 1,
      other: false,
    });
  }

  const sorted = [...aggregated.values()].sort(
    (left, right) =>
      right.totalWeight - left.totalWeight ||
      left.name.localeCompare(right.name),
  );
  const visible = sorted.slice(0, limit).map(({ recordIds, ...point }) => ({
    ...point,
    recordCount: recordIds.size,
  }));
  const remainder = sorted.slice(limit);
  if (remainder.length === 0) return visible;

  return [
    ...visible,
    {
      id: "other",
      name: "spaces.courseDetail.graph.other",
      fromHotWords: false,
      tags: [],
      totalWeight: remainder.reduce(
        (total, point) => total + point.totalWeight,
        0,
      ),
      recordCount: new Set(remainder.flatMap((point) => [...point.recordIds]))
        .size,
      conceptCount: remainder.length,
      other: true,
    },
  ];
}

/** 共享标签的具名知识点形成一条无向关系；「其他」不参与建图。 */
export function buildCourseKnowledgeRelations(
  points: AggregatedCourseKnowledgePoint[],
): CourseKnowledgeRelation[] {
  const namedPoints = points.filter((point) => !point.other);
  return namedPoints.flatMap((source, sourceIndex) =>
    namedPoints.slice(sourceIndex + 1).flatMap((target) => {
      const sharedTagCount = source.tags.filter((tag) =>
        target.tags.includes(tag),
      ).length;
      return sharedTagCount > 0
        ? [{ source: source.id, target: target.id, sharedTagCount }]
        : [];
    }),
  );
}

/** 中心课程节点 + 8 个知识主题节点（热词优先，不足用示意名称补齐）。 */
export function mockKnowledgeNodes(course: CourseDetail): KnowledgeNode[] {
  const seed = hash(course.id);
  const hotWords = (course.hot_words ?? []).filter((word) => word.trim());
  const nodes: KnowledgeNode[] = [
    {
      id: `${course.id}-core`,
      name: course.name,
      fromHotWords: false,
      core: true,
      state: "learning",
      x: 100,
      y: 80,
    },
  ];
  for (let index = 0; index < SATELLITE_ANGLES.length; index += 1) {
    const angle = (SATELLITE_ANGLES[index] * Math.PI) / 180;
    const radius = index % 2 === 0 ? 62 : 48;
    const percent = (seed >>> (index * 3)) % 100;
    const hotWord = hotWords[index];
    nodes.push({
      id: `${course.id}-topic-${index}`,
      name:
        hotWord ?? `spaces.courseDetail.mock.nodes.${index % NODE_NAME_COUNT}`,
      fromHotWords: Boolean(hotWord),
      core: false,
      state: masteryStateOf(percent),
      x: 100 + radius * Math.cos(angle),
      y: 80 + radius * Math.sin(angle),
    });
  }
  return nodes;
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

const GOAL_COUNT = 4;

export function mockLearningGoalKey(course: CourseDetail): string {
  return `spaces.courseDetail.mock.goals.${hash(`${course.id}-goal`) % GOAL_COUNT}`;
}

const SUBJECT_COUNT = 6;

export function mockSubjectKey(course: CourseDetail): string {
  return `spaces.courseDetail.mock.subjects.${hash(`${course.id}-subject`) % SUBJECT_COUNT}`;
}

export function mockInsightSuggestions(
  course: CourseDetail,
): InsightSuggestion[] {
  const seed = hash(`${course.id}-insights`);
  const stats = mockCourseCoreStats(course.id);
  const progress = mockCurrentProgress(course);
  const all: InsightSuggestion[] = [
    { key: "mastery", percent: stats.masteryPercent },
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
