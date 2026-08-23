import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type CaptureBatchAccepted =
  components["schemas"]["CaptureBatchAccepted"];

export const captureBatchApi = {
  create(courseId: string | null, files: File[]) {
    const body = new FormData();
    if (courseId) body.set("course_id", courseId);
    for (const file of files) body.append("files", file);
    return apiFetch<CaptureBatchAccepted>("/api/capture-batches", {
      method: "POST",
      body,
    });
  },
  createRecording(recordingSessionId: string) {
    const body = new FormData();
    body.set("recording_session_id", recordingSessionId);
    return apiFetch<CaptureBatchAccepted>("/api/capture-batches", {
      method: "POST",
      body,
    });
  },
};
