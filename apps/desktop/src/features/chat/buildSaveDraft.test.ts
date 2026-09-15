import { describe, expect, it } from "vitest";

import {
  buildSaveDraft,
  SAVE_DRAFT_MAX_LENGTH,
} from "@/features/chat/buildSaveDraft";

describe("buildSaveDraft", () => {
  it("取首个文本段并去掉行内 markdown 标记，链接保留文字", () => {
    const content =
      "## AOF 持久化\n\n`appendfsync` 控制**刷盘**频率，详见 [文档](https://example.com)。落盘策略见后文 [1]。";
    const draft = buildSaveDraft(content);
    expect(draft).toBe("AOF 持久化\n\n落盘策略见后文。");
  });

  it("跳过代码块段，提取带引用角的句子并去角标去重", () => {
    const content = [
      "AOF 是 Redis 的持久化方式。",
      "",
      "```python",
      "save 900 1",
      "```",
      "",
      "写入以追加方式进行 [1]。",
      "写入以追加方式进行 [1]。",
      "追加写带来较小的丢失窗口 [2]。",
      "没有引用的句子不入选。",
    ].join("\n");
    const draft = buildSaveDraft(content);
    const lines = draft.split("\n\n");
    expect(lines[0]).toBe("AOF 是 Redis 的持久化方式。");
    expect(lines).toContain("写入以追加方式进行。");
    expect(lines).toContain("追加写带来较小的丢失窗口。");
    expect(draft).not.toContain("[1]");
    expect(draft).not.toContain("没有引用的句子不入选。");
    expect(draft).not.toContain("save 900 1");
  });

  it("超长草稿截断到后端 2000 字上限内", () => {
    const paragraph = "这是用于撑长度的句子。".repeat(400);
    const draft = buildSaveDraft(paragraph);
    expect(draft.length).toBeLessThanOrEqual(SAVE_DRAFT_MAX_LENGTH);
  });

  it("纯代码块回答返回空串，由用户手填", () => {
    const content = "```\nselect * from t;\n```";
    expect(buildSaveDraft(content)).toBe("");
  });
});
