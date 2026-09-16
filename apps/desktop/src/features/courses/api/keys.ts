import type {
  BrainConceptListQuery,
  BrainRelationListQuery,
  CourseListQuery,
} from "@/features/courses/api/types";

export const courseKeys = {
  all: ["courses"] as const,
  lists: () => [...courseKeys.all, "list"] as const,
  list: (query: CourseListQuery = {}) =>
    [...courseKeys.lists(), query] as const,
  detail: (courseId: string) =>
    [...courseKeys.all, "detail", courseId] as const,
};

export const courseBrainKeys = {
  all: ["courseBrain"] as const,
  snapshot: (courseId: string) =>
    [...courseBrainKeys.all, "snapshot", courseId] as const,
  concepts: (courseId: string, query: BrainConceptListQuery = {}) =>
    [...courseBrainKeys.all, "concepts", courseId, query] as const,
  sources: (courseId: string, conceptId: string | null) =>
    [...courseBrainKeys.all, "sources", courseId, conceptId] as const,
  relations: (courseId: string, query: BrainRelationListQuery = {}) =>
    [...courseBrainKeys.all, "relations", courseId, query] as const,
};
