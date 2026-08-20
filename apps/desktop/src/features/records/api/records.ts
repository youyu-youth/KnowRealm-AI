import type {
  RecordOut,
  TranscriptReadOut,
} from "@/features/records/api/types";
import { apiFetch, apiFetchNoContent } from "@/services/http/client";

export const recordApi = {
  get: (recordId: string) => apiFetch<RecordOut>(`/api/records/${recordId}`),
  getTranscript: (recordId: string) =>
    apiFetch<TranscriptReadOut>(`/api/records/${recordId}/transcript`),
  delete: (recordId: string) =>
    apiFetchNoContent(`/api/records/${recordId}`, { method: "DELETE" }),
  listForCourse: (courseId: string) =>
    apiFetch<RecordOut[]>(`/api/courses/${courseId}/records`),
};
