import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type { Course, MasteryStatus } from "@/features/courses/api/types";

export function useActiveCourses(enabled = true): {
  courses: Course[];
  isPending: boolean;
  isError: boolean;
} {
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled,
  });
  return {
    courses: (courses.data ?? []).filter(
      (course) => course.status === "ACTIVE",
    ),
    isPending: courses.isPending,
    isError: courses.isError,
  };
}

/** 课程掌握度：不传 status 返回全量；status 只筛选列表，分布计数始终全量。 */
export function useCourseMastery(courseId: string, status?: MasteryStatus) {
  const query = status ? { status } : {};
  return useQuery({
    queryKey: courseKeys.mastery(courseId, query),
    queryFn: () => courseApi.mastery(courseId, query),
    placeholderData: keepPreviousData,
  });
}

/** Concept 掌握详情：选中概念时才发起查询（Dialog 打开即选中）。 */
export function useConceptMasteryDetail(
  courseId: string,
  conceptId: string | null,
) {
  return useQuery({
    queryKey: courseKeys.masteryDetail(courseId, conceptId ?? ""),
    // enabled 已排除 null；queryFn 签名要求非空参数，故收窄。
    queryFn: () => courseApi.masteryDetail(courseId, conceptId as string),
    enabled: conceptId !== null,
  });
}
