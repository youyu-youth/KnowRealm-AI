import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type DocumentImportAccepted =
  components["schemas"]["DocumentImportAccepted"];
export type ProcessingJobOut = components["schemas"]["ProcessingJobOut"];

export const documentImportKeys = {
  job: (jobId: string) => ["processing-jobs", jobId] as const,
};

export const documentImportApi = {
  create(courseId: string, file: File) {
    const body = new FormData();
    body.set("course_id", courseId);
    body.set("file", file);
    return apiFetch<DocumentImportAccepted>("/api/document-imports", {
      method: "POST",
      body,
    });
  },
  getJob: (jobId: string) =>
    apiFetch<ProcessingJobOut>(`/api/processing-jobs/${jobId}`),
};
