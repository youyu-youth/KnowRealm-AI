export type CourseTab =
  "overview" | "records" | "tests" | "map" | "gps" | "chat";

export function asCourseTab(value: unknown): CourseTab {
  return value === "records" ||
    value === "tests" ||
    value === "map" ||
    value === "gps" ||
    value === "chat"
    ? value
    : "overview";
}
