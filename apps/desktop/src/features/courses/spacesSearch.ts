import type {
  Course,
  CourseType,
  EducationStage,
  LearningContext,
} from "@/features/courses/api/types";
import {
  isCourseStatus,
  type CourseStatus,
} from "@/features/courses/courseOptions";

export type SpacesSort = "updated" | "created" | "name";
export type SpacesView = "grid" | "list" | "tracks";

/** 知识空间页的 URL 可恢复状态（筛选、排序与视图）。 */
export type SpacesSearch = {
  q?: string;
  learning_context?: LearningContext;
  status?: CourseStatus;
  sort?: SpacesSort;
  view?: SpacesView;
  education_stage?: EducationStage;
  course_type?: CourseType;
};

export const spacesSorts: SpacesSort[] = ["updated", "created", "name"];
export const spacesViews: SpacesView[] = ["grid", "list", "tracks"];

export function isSpacesSort(value: unknown): value is SpacesSort {
  return typeof value === "string" && spacesSorts.includes(value as SpacesSort);
}

export function isSpacesView(value: unknown): value is SpacesView {
  return typeof value === "string" && spacesViews.includes(value as SpacesView);
}

export function isSpacesFilterStatus(value: unknown): value is CourseStatus {
  return isCourseStatus(value);
}

function matchesQuery(course: Course, query: string): boolean {
  if (!query) return true;
  return course.name.toLocaleLowerCase().includes(query);
}

/** 客户端过滤：课程体量小，一次拉全量后本地筛选，避免多次往返。 */
export function filterSpacesCourses(
  courses: Course[],
  search: SpacesSearch,
): Course[] {
  const query = search.q?.trim().toLocaleLowerCase() ?? "";
  // 状态默认 ACTIVE：归档课程只在显式切换后出现（与参考界面一致）。
  const status = search.status ?? "ACTIVE";
  return courses.filter((course) => {
    if (!matchesQuery(course, query)) return false;
    if (
      search.learning_context &&
      course.learning_context !== search.learning_context
    )
      return false;
    if (course.status !== status) return false;
    if (
      search.education_stage &&
      course.education_stage !== search.education_stage
    )
      return false;
    if (search.course_type && course.course_type !== search.course_type)
      return false;
    return true;
  });
}

export function sortSpacesCourses(
  courses: Course[],
  sort: SpacesSort = "updated",
): Course[] {
  const sorted = [...courses];
  if (sort === "name") {
    return sorted.sort((left, right) => left.name.localeCompare(right.name));
  }
  const key = sort === "created" ? "created_at" : "updated_at";
  return sorted.sort(
    (left, right) => Date.parse(right[key]) - Date.parse(left[key]),
  );
}

/** 过滤 + 排序后的可见课程（列表与计数共用同一事实）。 */
export function visibleSpacesCourses(
  courses: Course[],
  search: SpacesSearch,
): Course[] {
  return sortSpacesCourses(
    filterSpacesCourses(courses, search),
    search.sort ?? "updated",
  );
}

export function hasSpacesFilters(search: SpacesSearch): boolean {
  return Boolean(
    search.q ||
    search.learning_context ||
    search.status ||
    search.education_stage ||
    search.course_type,
  );
}
