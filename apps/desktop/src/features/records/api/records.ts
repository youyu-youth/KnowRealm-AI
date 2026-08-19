import type { RecordOut } from "@/features/records/api/types";
import { apiFetch } from "@/services/http/client";

export const recordApi = {
  listForCourse: (courseId: string) =>
    apiFetch<RecordOut[]>(`/api/courses/${courseId}/records`),
};
