import { describe, expect, it } from "vitest";
import {
  COMMENTARY_ICON,
  TOOL_ICON_FALLBACK,
  TOOL_ICONS,
} from "@/features/chat/toolIcons";

describe("过程行图标映射", () => {
  it("每个工具一个专属图标，且不与兜底/思考图标重复", () => {
    const icons = Object.values(TOOL_ICONS);
    expect(new Set(icons).size).toBe(icons.length);
    expect(icons).not.toContain(TOOL_ICON_FALLBACK);
    expect(icons).not.toContain(COMMENTARY_ICON);
    expect(TOOL_ICON_FALLBACK).not.toBe(COMMENTARY_ICON);
  });

  it("覆盖文案映射涉及的工具与已退役的 search_transcript", () => {
    for (const tool of [
      "search_library",
      "search_courses",
      "search_transcript",
      "web_search",
      "list_course_records",
      "create_course",
    ]) {
      expect(TOOL_ICONS[tool]).toBeDefined();
    }
  });
});
