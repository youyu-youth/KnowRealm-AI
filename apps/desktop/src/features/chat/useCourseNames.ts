import { useQuery } from "@tanstack/react-query";
import { courseKeys } from "@/features/courses/api/keys";
import { courseApi } from "@/features/courses/api/courses";

/** 课程名速查表（课程范围标识用）：课程列表已在侧栏 / 空间页共用缓存。 */
export function useCourseNames() {
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
  });
  return courses.data
    ? new Map(courses.data.map((course) => [course.id, course.name]))
    : new Map<string, string>();
}
