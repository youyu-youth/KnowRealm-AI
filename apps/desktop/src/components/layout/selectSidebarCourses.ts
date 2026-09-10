import type { Course } from "@/features/courses/api/types";

export function selectSidebarCourses(
  courses: Course[],
  activeCourseId?: string,
) {
  return [...courses]
    .sort((left, right) => {
      if (left.id === activeCourseId) return -1;
      if (right.id === activeCourseId) return 1;
      return 0;
    })
    .slice(0, 5);
}
