import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type AudioImportAccepted = components["schemas"]["AudioImportAccepted"];

export const audioImportApi = {
  create(courseId: string | null, file: File) {
    const body = new FormData();
    if (courseId) body.set("course_id", courseId);
    body.set("file", file);
    return apiFetch<AudioImportAccepted>("/api/audio-imports", {
      method: "POST",
      body,
    });
  },
};
