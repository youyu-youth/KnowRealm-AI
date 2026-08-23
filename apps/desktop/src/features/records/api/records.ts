import type {
  ProcessingJobOut,
  RecordJobsOut,
  RecordOut,
  SummaryReadOut,
  TranscriptOut,
  TranscriptReadOut,
} from "@/features/records/api/types";
import { createParser } from "eventsource-parser";
import {
  apiFetch,
  apiFetchNoContent,
  apiRequest,
} from "@/services/http/client";
import type { components } from "@knowrealm/api-types";

export const recordApi = {
  get: (recordId: string) => apiFetch<RecordOut>(`/api/records/${recordId}`),
  getTranscript: (recordId: string) =>
    apiFetch<TranscriptReadOut>(`/api/records/${recordId}/transcript`),
  getJobs: (recordId: string) =>
    apiFetch<RecordJobsOut>(`/api/records/${recordId}/jobs`),
  getSummary: (recordId: string) =>
    apiFetch<SummaryReadOut>(`/api/records/${recordId}/summary`),
  submitSummary: (recordId: string) =>
    apiFetch<components["schemas"]["SummaryJobAccepted"]>(
      `/api/records/${recordId}/summary-jobs`,
      { method: "POST" },
    ),
  updateTranscript(
    recordId: string,
    body: components["schemas"]["TranscriptUpdateRequest"],
  ) {
    return apiFetch<TranscriptOut>(`/api/records/${recordId}/transcript`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  retryJob(jobId: string, recordId: string) {
    const body: components["schemas"]["ProcessingJobRetryRequest"] = {
      record_id: recordId,
    };
    return apiFetch<ProcessingJobOut>(`/api/processing-jobs/${jobId}/retries`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  async subscribe(
    recordId: string,
    signal: AbortSignal | undefined,
    onOpen: () => void,
    onInvalidate: () => void,
  ) {
    const response = await apiRequest(`/api/records/${recordId}/events`, {
      headers: { Accept: "text/event-stream" },
      signal,
    });
    if (!response.body) throw new Error("Record 事件流没有响应正文");
    onOpen();
    const parser = createParser({
      maxBufferSize: 1_024,
      onEvent: (event) => {
        if (event.event === "invalidate") onInvalidate();
      },
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) throw new Error("Record 事件流已断开");
      parser.feed(decoder.decode(value, { stream: true }));
    }
  },
  delete: (recordId: string) =>
    apiFetchNoContent(`/api/records/${recordId}`, { method: "DELETE" }),
  listForCourse: (courseId: string) =>
    apiFetch<RecordOut[]>(`/api/courses/${courseId}/records`),
};
