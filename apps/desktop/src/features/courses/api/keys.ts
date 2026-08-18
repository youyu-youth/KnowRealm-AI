import type { CourseListQuery } from "@/features/courses/api/types";

export const courseKeys = {
  all: ["courses"] as const,
  lists: () => [...courseKeys.all, "list"] as const,
  list: (query: CourseListQuery = {}) =>
    [...courseKeys.lists(), query] as const,
  detail: (courseId: string) =>
    [...courseKeys.all, "detail", courseId] as const,
};
