export const recordKeys = {
  all: ["records"] as const,
  detail: (recordId: string) =>
    [...recordKeys.all, "detail", recordId] as const,
  transcript: (recordId: string) =>
    [...recordKeys.all, "transcript", recordId] as const,
  jobs: (recordId: string) => [...recordKeys.all, "jobs", recordId] as const,
  summary: (recordId: string) =>
    [...recordKeys.all, "summary", recordId] as const,
  courseList: (courseId: string) =>
    [...recordKeys.all, "course", courseId] as const,
};
