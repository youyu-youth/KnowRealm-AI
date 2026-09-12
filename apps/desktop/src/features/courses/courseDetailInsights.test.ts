import { describe, expect, it } from "vitest";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  aggregateCourseKnowledgePoints,
  buildCourseKnowledgeRelations,
  masteryStateOf,
  mockChapterMastery,
  mockCourseCoreStats,
  mockCurrentProgress,
  mockInsightSuggestions,
  mockKnowledgeNodes,
  mockCourseKnowledgePoints,
  mockRecommendedPoints,
} from "@/features/courses/courseDetailInsights";

const course: CourseDetail = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: "理解进程、内存与文件系统。",
  status: "ACTIVE",
  hot_words: ["进程调度", "虚拟内存"],
  created_at: "2026-08-17T00:00:00.000000Z",
  updated_at: "2026-08-18T00:00:00.000000Z",
};

describe("courseDetailInsights 示意数据", () => {
  it("同一课程 id 重复生成结果稳定一致", () => {
    expect(mockCourseCoreStats(course.id)).toEqual(
      mockCourseCoreStats(course.id),
    );
    expect(mockChapterMastery(course)).toEqual(mockChapterMastery(course));
    expect(mockKnowledgeNodes(course)).toEqual(mockKnowledgeNodes(course));
  });

  it("掌握状态按百分比分档：≥80 已掌握、>0 学习中、0 未开始", () => {
    expect(masteryStateOf(88)).toBe("mastered");
    expect(masteryStateOf(62)).toBe("learning");
    expect(masteryStateOf(0)).toBe("untouched");
  });

  it("知识图谱为 1 个中心节点 + 8 个主题节点，热词优先用作节点名", () => {
    const nodes = mockKnowledgeNodes(course);
    expect(nodes).toHaveLength(9);
    expect(nodes.filter((node) => node.core)).toHaveLength(1);
    expect(nodes[0].name).toBe(course.name);
    expect(nodes[1].name).toBe("进程调度");
    expect(nodes[1].fromHotWords).toBe(true);
    expect(nodes[3].fromHotWords).toBe(false);
  });

  it("课程知识点按同名合并权重并将 Top 12 之外汇总为其他", () => {
    const points = mockCourseKnowledgePoints(course);
    expect(points).toEqual(mockCourseKnowledgePoints(course));
    expect(new Set(points.map((point) => point.recordId)).size).toBeGreaterThan(
      1,
    );

    const aggregated = aggregateCourseKnowledgePoints(points);
    const visible = aggregated.filter((point) => !point.other);
    const other = aggregated.find((point) => point.other);

    expect(visible).toHaveLength(12);
    expect(other?.conceptCount).toBe(2);
    expect(aggregated.reduce((sum, point) => sum + point.totalWeight, 0)).toBe(
      points.reduce((sum, point) => sum + point.importance, 0),
    );
    expect(visible[0].totalWeight).toBeGreaterThanOrEqual(
      visible[visible.length - 1].totalWeight,
    );
  });

  it("课程知识关系仅连接共享标签的具名知识点", () => {
    const aggregated = aggregateCourseKnowledgePoints(
      mockCourseKnowledgePoints(course),
    );
    const relations = buildCourseKnowledgeRelations(aggregated);
    const pointsById = new Map(aggregated.map((point) => [point.id, point]));

    expect(relations.length).toBeGreaterThan(0);
    for (const relation of relations) {
      expect(pointsById.get(relation.source)?.other).toBe(false);
      expect(pointsById.get(relation.target)?.other).toBe(false);
      expect(relation.sharedTagCount).toBeGreaterThan(0);
    }
  });

  it("章级掌握数量与核心统计章节数一致，掌握度整体递减", () => {
    const chapters = mockChapterMastery(course);
    expect(chapters).toHaveLength(mockCourseCoreStats(course.id).chapters);
    expect(chapters[0].percent).toBeGreaterThan(
      chapters[chapters.length - 1].percent,
    );
  });

  it("当前进度取首个未掌握章节", () => {
    const progress = mockCurrentProgress(course);
    expect(progress.state).not.toBe("mastered");
    expect(progress.index).toBeGreaterThanOrEqual(1);
  });

  it("洞察建议固定 3 条且 key 不重复", () => {
    const suggestions = mockInsightSuggestions(course);
    expect(suggestions).toHaveLength(3);
    expect(new Set(suggestions.map((item) => item.key)).size).toBe(3);
  });

  it("重点推荐按批次轮转，每批 3 条且批次间内容变化", () => {
    const first = mockRecommendedPoints(course, 0);
    const second = mockRecommendedPoints(course, 1);
    expect(first).toHaveLength(3);
    expect(first.map((item) => item.titleKey)).not.toEqual(
      second.map((item) => item.titleKey),
    );
  });
});
