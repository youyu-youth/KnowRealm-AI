export const recordKeys = {
  all: ["records"] as const,
  courseList: (courseId: string) =>
    [...recordKeys.all, "course", courseId] as const,
};
