export type CourseTab = "overview" | "records" | "tests";

export function asCourseTab(value: unknown): CourseTab {
  return value === "records" || value === "tests" ? value : "overview";
}
