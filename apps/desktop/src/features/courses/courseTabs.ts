export type CourseTab =
  "overview" | "chain" | "records" | "tests" | "map" | "gps" | "chat";

export function asCourseTab(value: unknown): CourseTab {
  return value === "chain" ||
    value === "records" ||
    value === "tests" ||
    value === "map" ||
    value === "gps" ||
    value === "chat"
    ? value
    : "overview";
}
