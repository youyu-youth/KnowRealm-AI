import { useQuery } from "@tanstack/react-query";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type { Course } from "@/features/courses/api/types";

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
