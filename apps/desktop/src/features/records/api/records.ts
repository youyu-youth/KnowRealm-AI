import type {
  InboxRecordOut,
  ProcessingJobOut,
  KnowledgePointReadOut,
  QuizGenerateRequest,
  QuizOut,
  QuizReadOut,
  RecordJobsOut,
  RecordOut,
  ReviewMaterialReadOut,
  SummaryReadOut,
  TodoOut,
  TodoReadOut,
  TranscriptOut,
  TranscriptReadOut,
  TranscriptSegmentOut,
  DocumentSegmentOut,
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
  listInbox: () => apiFetch<InboxRecordOut[]>("/api/inbox"),
  classify: (recordId: string, courseId: string) =>
    apiFetch<RecordOut>(`/api/records/${recordId}/classification`, {
      method: "POST",
      body: JSON.stringify({ course_id: courseId }),
    }),
  upgrade: (recordId: string, courseId: string | null) =>
    apiFetch<components["schemas"]["RecordUpgradeAccepted"]>(
      `/api/records/${recordId}/upgrade`,
      { method: "POST", body: JSON.stringify({ course_id: courseId }) },
    ),
  getTranscript: (recordId: string) =>
    apiFetch<TranscriptReadOut>(`/api/records/${recordId}/transcript`),
  getTranscriptSegments: (recordId: string) =>
    apiFetch<TranscriptSegmentOut[]>(
      `/api/records/${recordId}/transcript/segments`,
    ),
  getDocumentSegments: (recordId: string) =>
    apiFetch<DocumentSegmentOut[]>(
      `/api/records/${recordId}/document-segments`,
    ),
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
  adoptQuizBatch(recordId: string, batchId: string) {
    return apiFetch<QuizReadOut>(
      `/api/records/${recordId}/quiz-batches/${batchId}/confirmations`,
      { method: "POST" },
    );
  },
  setQuizConcept(
    recordId: string,
    quizId: string,
    body: components["schemas"]["QuizConceptUpdateRequest"],
  ) {
    return apiFetch<QuizOut>(
      `/api/records/${recordId}/quizzes/${quizId}/concept`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    );
  },
  answerObjectiveQuiz(
    recordId: string,
    quizId: string,
    body: components["schemas"]["QuizObjectiveAnswerRequest"],
  ) {
    return apiFetch<components["schemas"]["QuizOut"]>(
      `/api/records/${recordId}/quizzes/${quizId}/answers`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  answerShortQuiz(
    recordId: string,
    quizId: string,
    body: components["schemas"]["QuizShortAnswerRequest"],
  ) {
    return apiFetch<components["schemas"]["QuizOut"]>(
      `/api/records/${recordId}/quizzes/${quizId}/answers`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  selfAssessShortQuiz(
    recordId: string,
    quizId: string,
    body: components["schemas"]["QuizSelfAssessmentRequest"],
  ) {
    return apiFetch<components["schemas"]["QuizOut"]>(
      `/api/records/${recordId}/quizzes/${quizId}/self-assessments`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  getTodos: (recordId: string) =>
    apiFetch<TodoReadOut>(`/api/records/${recordId}/todos`),
  getReviewMaterial: (recordId: string) =>
    apiFetch<ReviewMaterialReadOut>(`/api/records/${recordId}/review-material`),
  submitReviewMaterial: (recordId: string) =>
    apiFetch<components["schemas"]["ReviewMaterialJobAccepted"]>(
      `/api/records/${recordId}/review-material-jobs`,
      { method: "POST" },
    ),
  getReviewMaterials: (recordId: string) =>
    apiFetch<components["schemas"]["ReviewMaterialOut"][]>(
      `/api/records/${recordId}/review-materials`,
    ),
  adjustReviewMaterial(
    recordId: string,
    body: components["schemas"]["ReviewMaterialAdjustRequest"],
  ) {
    return apiFetch<components["schemas"]["ReviewMaterialJobAccepted"]>(
      `/api/records/${recordId}/review-material-adjustments`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  confirmReviewMaterial(recordId: string) {
    return apiFetch<components["schemas"]["ReviewMaterialOut"]>(
      `/api/records/${recordId}/review-material-confirmations`,
      { method: "POST" },
    );
  },
  editReviewMaterial(
    recordId: string,
    body: components["schemas"]["ReviewMaterialContent"],
  ) {
    return apiFetch<components["schemas"]["ReviewMaterialOut"]>(
      `/api/records/${recordId}/review-material`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },
  submitTodoGeneration(recordId: string) {
    return apiFetch<components["schemas"]["TodoJobAccepted"]>(
      `/api/records/${recordId}/todo-jobs`,
      { method: "POST" },
    );
  },
  discardTodoBatch(recordId: string, batchId: string) {
    return apiFetch<TodoReadOut>(
      `/api/records/${recordId}/todo-batches/${batchId}/discards`,
      { method: "POST" },
    );
  },
  adoptTodoBatch(recordId: string, batchId: string) {
    return apiFetch<TodoReadOut>(
      `/api/records/${recordId}/todo-batches/${batchId}/confirmations`,
      { method: "POST" },
    );
  },
  createTodo(recordId: string, content: string) {
    return apiFetch<TodoOut>(`/api/records/${recordId}/todos`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },
  updateTodo(recordId: string, todoId: string, content: string) {
    return apiFetch<TodoOut>(`/api/records/${recordId}/todos/${todoId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    });
  },
  deleteTodo(recordId: string, todoId: string) {
    return apiFetchNoContent(`/api/records/${recordId}/todos/${todoId}`, {
      method: "DELETE",
    });
  },
  toggleTodo(
    recordId: string,
    todoId: string,
    status: components["schemas"]["TodoStatus"],
  ) {
    return apiFetch<TodoOut>(
      `/api/records/${recordId}/todos/${todoId}/toggles`,
      { method: "POST", body: JSON.stringify({ status }) },
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
