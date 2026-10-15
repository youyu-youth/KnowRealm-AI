import type { LearningResume } from "@/features/today/api/resume";

export type ResumeTarget = Pick<
  LearningResume,
  "kind" | "target_id" | "course_id" | "record_tab"
>;

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const recordPath = new RegExp(`^/records/(${UUID})$`, "i");
const testPath = new RegExp(`^/spaces/(${UUID})/tests/(${UUID})$`, "i");
const chatPath = new RegExp(`^/chat/(${UUID})$`, "i");

export function parseResumeHref(href: string): ResumeTarget | null {
  if (href.split("?").length > 2) return null;
  const [path, query] = href.split("?");
  const record = recordPath.exec(path);
  if (record) {
    const params = new URLSearchParams(query);
    if (
      [...params.keys()].some((key) => key !== "tab") ||
      params.getAll("tab").length > 1
    )
      return null;
    const tab = params.get("tab") ?? "summary";
    if (
      tab !== "summary" &&
      tab !== "transcript" &&
      tab !== "knowledge-points" &&
      tab !== "quiz" &&
      tab !== "review" &&
      tab !== "todo"
    )
      return null;
    return {
      kind: "RECORD",
      target_id: record[1],
      course_id: null,
      record_tab: tab,
    };
  }
  if (query !== undefined) return null;
  const test = testPath.exec(path);
  if (test)
    return {
      kind: "QUIZ_TEST",
      target_id: test[2],
      course_id: test[1],
      record_tab: null,
    };
  const chat = chatPath.exec(path);
  return chat
    ? {
        kind: "CHAT_SESSION",
        target_id: chat[1],
        course_id: null,
        record_tab: null,
      }
    : null;
}
