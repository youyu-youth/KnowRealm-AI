import type {
  ProcessingJobOut,
  KnowledgePointReadOut,
  QuizGenerateRequest,
  QuizReadOut,
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
  getKnowledgePoints: (recordId: string) =>
    apiFetch<KnowledgePointReadOut>(
      `/api/records/${recordId}/knowledge-points`,
    ),
  createKnowledgePoint(
    recordId: string,
    body: components["schemas"]["KnowledgePointWriteRequest"],
  ) {
    return apiFetch<components["schemas"]["KnowledgePointOut"]>(
      `/api/records/${recordId}/knowledge-points`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  updateKnowledgePoint(
    recordId: string,
    itemId: string,
    body: components["schemas"]["KnowledgePointWriteRequest"],
  ) {
    return apiFetch<components["schemas"]["KnowledgePointOut"]>(
      `/api/records/${recordId}/knowledge-points/${itemId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },
  deleteKnowledgePoint(recordId: string, itemId: string) {
    return apiFetchNoContent(
      `/api/records/${recordId}/knowledge-points/${itemId}`,
      { method: "DELETE" },
    );
  },
  confirmKnowledgePointBatch(recordId: string, batchId: string) {
    return apiFetch<KnowledgePointReadOut>(
      `/api/records/${recordId}/knowledge-point-batches/${batchId}/confirmations`,
      { method: "POST" },
    );
  },
  discardKnowledgePointBatch(recordId: string, batchId: string) {
    return apiFetch<KnowledgePointReadOut>(
      `/api/records/${recordId}/knowledge-point-batches/${batchId}/discards`,
      { method: "POST" },
    );
  },
  submitKnowledgePoints: (recordId: string) =>
    apiFetch<components["schemas"]["KnowledgePointJobAccepted"]>(
      `/api/records/${recordId}/knowledge-point-jobs`,
      { method: "POST" },
    ),
  getQuizzes: (recordId: string) =>
    apiFetch<QuizReadOut>(`/api/records/${recordId}/quizzes`),
  submitQuizGeneration(recordId: string, body: QuizGenerateRequest) {
    return apiFetch<components["schemas"]["QuizJobAccepted"]>(
      `/api/records/${recordId}/quiz-jobs`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  discardQuizBatch(recordId: string, batchId: string) {
    return apiFetch<QuizReadOut>(
      `/api/records/${recordId}/quiz-batches/${batchId}/discards`,
      { method: "POST" },
    );
  },
  submitSummary: (recordId: string) =>
    apiFetch<components["schemas"]["SummaryJobAccepted"]>(
      `/api/records/${recordId}/summary-jobs`,
      { method: "POST" },
    ),
  adjustSummary(
    recordId: string,
    body: components["schemas"]["SummaryAdjustRequest"],
  ) {
    return apiFetch<components["schemas"]["SummaryJobAccepted"]>(
      `/api/records/${recordId}/summary-adjustments`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  confirmSummary(recordId: string, summaryId: string) {
    return apiFetch<components["schemas"]["SummaryConfirmOut"]>(
      `/api/records/${recordId}/summary-confirmations`,
      { method: "POST", body: JSON.stringify({ summary_id: summaryId }) },
    );
  },
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
