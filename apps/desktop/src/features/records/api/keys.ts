export const recordKeys = {
  all: ["records"] as const,
  detail: (recordId: string) =>
    [...recordKeys.all, "detail", recordId] as const,
  transcript: (recordId: string) =>
    [...recordKeys.all, "transcript", recordId] as const,
  jobs: (recordId: string) => [...recordKeys.all, "jobs", recordId] as const,
  summary: (recordId: string) =>
    [...recordKeys.all, "summary", recordId] as const,
  knowledgePoints: (recordId: string) =>
    [...recordKeys.all, "knowledge-points", recordId] as const,
  quizzes: (recordId: string) =>
    [...recordKeys.all, "quizzes", recordId] as const,
  todos: (recordId: string) => [...recordKeys.all, "todos", recordId] as const,
  reviewMaterial: (recordId: string) =>
    [...recordKeys.all, "review-material", recordId] as const,
  reviewMaterials: (recordId: string) =>
    [...recordKeys.all, "review-materials", recordId] as const,
  courseList: (courseId: string) =>
    [...recordKeys.all, "course", courseId] as const,
  inbox: () => [...recordKeys.all, "inbox"] as const,
};
