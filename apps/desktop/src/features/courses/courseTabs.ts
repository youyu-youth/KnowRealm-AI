export type CourseTab = "overview" | "records";

export function asCourseTab(value: unknown): CourseTab {
  return value === "records" ? "records" : "overview";
}
