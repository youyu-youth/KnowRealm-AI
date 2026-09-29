import { describe, expect, it } from "vitest";

import {
  buildSaveDraft,
  SAVE_DRAFT_MAX_LENGTH,
} from "@/features/chat/buildSaveDraft";

describe("buildSaveDraft", () => {
  it("保留全部文本段并去掉行内 markdown 标记与引用角标", () => {
    const content =
      "## AOF 持久化\n\n`appendfsync` 控制**刷盘**频率，详见 [文档](https://example.com)。落盘策略见后文 [1]。\n\n写入以追加方式进行，先写内存缓冲再刷盘。";
    const draft = buildSaveDraft(content);
    expect(draft).toBe(
      "AOF 持久化\n\nappendfsync 控制刷盘频率，详见 文档。落盘策略见后文。\n\n写入以追加方式进行，先写内存缓冲再刷盘。",
    );
  });

  it("保留代码块内容（去围栏标记、内部原样），含被空行切开的代码块", () => {
    const content = [
      "AOF 是 Redis 的持久化方式。",
      "",
      "```python",
      "save 900 1",
      "",
      "save 300 10",
      "```",
      "",
      "写入以追加方式进行。",
    ].join("\n");
    const draft = buildSaveDraft(content);
    const blocks = draft.split("\n\n");
    expect(blocks[0]).toBe("AOF 是 Redis 的持久化方式。");
    expect(blocks[1]).toBe("save 900 1");
    expect(blocks[2]).toBe("save 300 10");
    expect(blocks[3]).toBe("写入以追加方式进行。");
  });

  it("纯代码块回答返回去围栏后的代码内容", () => {
    const content = "```\nselect * from t;\n```";
    expect(buildSaveDraft(content)).toBe("select * from t;");
  });

  it("剥离计划草案 JSON 段（与渲染路径对齐）", () => {
    const content = [
      "先给出草案：",
      "",
      "```json",
      '{"phases": [{"items": [{"topic": "AOF"}]}]}',
      "```",
      "",
      "以上是本周期计划。",
    ].join("\n");
    const draft = buildSaveDraft(content);
    expect(draft).toBe("先给出草案：\n\n以上是本周期计划。");
  });

  it("超长草稿截断到后端 2000 字上限内", () => {
    const paragraph = "这是用于撑长度的句子。".repeat(400);
    const draft = buildSaveDraft(paragraph);
    expect(draft.length).toBeLessThanOrEqual(SAVE_DRAFT_MAX_LENGTH);
  });
});
