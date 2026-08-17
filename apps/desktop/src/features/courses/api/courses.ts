import { apiFetch } from "@/services/http/client";
import type { Course, CourseCreate } from "@/features/courses/api/types";

export const courseApi = {
  list: () => apiFetch<Course[]>("/api/courses"),
  create: (payload: CourseCreate) =>
    apiFetch<Course>("/api/courses", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
