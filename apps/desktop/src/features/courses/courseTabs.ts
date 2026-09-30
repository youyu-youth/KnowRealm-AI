export type CourseTab =
  "overview" | "chain" | "plan" | "records" | "tests" | "map" | "gps" | "chat";

export function asCourseTab(value: unknown): CourseTab {
  return value === "chain" ||
    value === "plan" ||
    value === "records" ||
    value === "tests" ||
    value === "map" ||
    value === "gps" ||
    value === "chat"
    ? value
    : "overview";
}
