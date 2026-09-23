import { apiFetch, apiFetchNoContent } from "@/services/http/client";
import type {
  Course,
  CourseCreate,
  CourseDetail,
  CourseListQuery,
  CourseMastery,
  CourseMasteryQuery,
  ConceptMasteryDetail,
  CourseUpdate,
} from "@/features/courses/api/types";

export const courseApi = {
  list: (query: CourseListQuery = {}) => {
    const search = new URLSearchParams();
    if (query.q) search.set("q", query.q);
    if (query.education_stage)
      search.set("education_stage", query.education_stage);
    if (query.course_type) search.set("course_type", query.course_type);
    return apiFetch<Course[]>(
      `/api/courses${search.size > 0 ? `?${search}` : ""}`,
    );
  },
  create: (payload: CourseCreate) =>
    apiFetch<Course>("/api/courses", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  get: (courseId: string) => apiFetch<CourseDetail>(`/api/courses/${courseId}`),
  mastery: (courseId: string, query: CourseMasteryQuery = {}) => {
    const search = new URLSearchParams();
    if (query.status) search.set("status", query.status);
    return apiFetch<CourseMastery>(
      `/api/courses/${courseId}/mastery${search.size > 0 ? `?${search}` : ""}`,
    );
  },
  masteryDetail: (courseId: string, conceptId: string) =>
    apiFetch<ConceptMasteryDetail>(
      `/api/courses/${courseId}/mastery/concepts/${conceptId}`,
    ),
  update: (courseId: string, payload: CourseUpdate) =>
    apiFetch<Course>(`/api/courses/${courseId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  archive: (courseId: string) =>
    apiFetch<Course>(`/api/courses/${courseId}/archive`, { method: "POST" }),
  unarchive: (courseId: string) =>
    apiFetch<Course>(`/api/courses/${courseId}/unarchive`, { method: "POST" }),
  delete: (courseId: string) =>
    apiFetchNoContent(`/api/courses/${courseId}`, { method: "DELETE" }),
};
