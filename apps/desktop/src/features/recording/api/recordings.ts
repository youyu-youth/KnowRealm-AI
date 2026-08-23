import type { components } from "@knowrealm/api-types";
import { apiFetch, apiFetchNoContent } from "@/services/http/client";

export type RecordingSession = components["schemas"]["RecordingSessionOut"];
export type RecordingChunkAccepted =
  components["schemas"]["RecordingChunkAccepted"];
export type RecordingTargetState =
  components["schemas"]["RecordingChunkTargetState"];

export const recordingApi = {
  list: () => apiFetch<RecordingSession[]>("/api/recording-sessions"),
  create: (courseId: string | null, title: string) =>
    apiFetch<RecordingSession>("/api/recording-sessions", {
      method: "POST",
      body: JSON.stringify({ course_id: courseId, title: title || null }),
    }),
  appendChunk(
    sessionId: string,
    sequenceNo: number,
    durationMs: number,
    targetState: RecordingTargetState,
    blob: Blob,
  ) {
    const body = new FormData();
    body.set("sequence_no", String(sequenceNo));
    body.set("duration_ms", String(durationMs));
    body.set("target_state", targetState);
    body.set("file", blob, `${sequenceNo}.webm`);
    return apiFetch<RecordingChunkAccepted>(
      `/api/recording-sessions/${sessionId}/chunks`,
      { method: "POST", body },
    );
  },
  update: (sessionId: string, targetState: "RECORDING" | "FINALIZING") =>
    apiFetch<RecordingSession>(`/api/recording-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ target_state: targetState }),
    }),
  abandon: (sessionId: string) =>
    apiFetchNoContent(`/api/recording-sessions/${sessionId}`, {
      method: "DELETE",
    }),
};
