export const recordKeys = {
  all: ["records"] as const,
  detail: (recordId: string) =>
    [...recordKeys.all, "detail", recordId] as const,
  transcript: (recordId: string) =>
    [...recordKeys.all, "transcript", recordId] as const,
  courseList: (courseId: string) =>
    [...recordKeys.all, "course", courseId] as const,
};
