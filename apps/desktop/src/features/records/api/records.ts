import type { RecordOut } from "@/features/records/api/types";
import { apiFetch } from "@/services/http/client";

export const recordApi = {
  get: (recordId: string) => apiFetch<RecordOut>(`/api/records/${recordId}`),
  listForCourse: (courseId: string) =>
    apiFetch<RecordOut[]>(`/api/courses/${courseId}/records`),
};
