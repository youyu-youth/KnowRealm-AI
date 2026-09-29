import { describe, expect, it } from "vitest";
import {
  planDraftStreamingView,
  stripPlanDraftBlocks,
} from "@/features/chat/planDraftJson";

function draftJson(itemCount = 1): string {
  const items = Array.from({ length: itemCount }, (_, index) => ({
    action_type: "CUSTOM",
    content: `任务 ${index + 1}`,
    estimated_minutes: 30,
    reason: "理由",
    record_id: null,
    concept_id: null,
    scheduled_date: "2026-09-29",
  }));
  return JSON.stringify({
    goal_id: "90000000-0000-4000-8000-000000000001",
    phases: [{ title: "第一阶段", items }],
  });
}

describe("stripPlanDraftBlocks（位置无关草案剥离，三轮形态回归）", () => {
  it("一轮形态：正文整体即草案 JSON → 命中且 rest 为空（折叠块场景）", () => {
    const stripped = stripPlanDraftBlocks(`  ${draftJson(3)}  `);
    expect(stripped).not.toBeNull();
    expect(stripped?.rest).toBe("");
    expect(stripped?.blocks[0].itemCount).toBe(3);
    expect(stripped?.blocks[0].json).toBe(draftJson(3));
  });

  it("二轮形态：JSON 在前 + 中文复述在后 → 剥离 JSON 只剩中文", () => {
    const stripped = stripPlanDraftBlocks(
      `${draftJson(2)}\n已按目标生成草案，共 5 个阶段，请过目。`,
    );
    expect(stripped?.rest).toBe("已按目标生成草案，共 5 个阶段，请过目。");
    expect(stripped?.blocks[0].itemCount).toBe(2);
  });

  it("三轮形态：中文在前 + JSON 在后（真机 09-29 复现）→ 剥离 JSON 只剩中文", () => {
    const stripped = stripPlanDraftBlocks(
      `我先确认目标，再重新生成草案。${draftJson(4)}`,
    );
    expect(stripped?.rest).toBe("我先确认目标，再重新生成草案。");
    expect(stripped?.blocks[0].itemCount).toBe(4);
  });

  it("JSON 夹在两段中文中间 → 两段中文都保留", () => {
    const stripped = stripPlanDraftBlocks(
      `我先确认目标。${draftJson(1)}已按目标生成草案，请过目。`,
    );
    expect(stripped?.rest).toBe("我先确认目标。已按目标生成草案，请过目。");
  });

  it("```json 围栏包裹（任意位置，含语言标记行）→ 整段围栏移除", () => {
    const stripped = stripPlanDraftBlocks(
      `草案如下：\n\`\`\`json\n${draftJson(2)}\n\`\`\`\n请过目。`,
    );
    expect(stripped?.rest).toContain("草案如下");
    expect(stripped?.rest).toContain("请过目");
    expect(stripped?.rest).not.toContain("```");
    expect(stripped?.blocks[0].itemCount).toBe(2);
  });

  it("JSON 内含转义引号与嵌套花括号不误判边界", () => {
    const tricky = JSON.stringify({
      phases: [{ title: '含"}"与\\', items: [{ note: "a{b}c" }] }],
    });
    const stripped = stripPlanDraftBlocks(`前文。${tricky}后文。`);
    expect(stripped?.rest).toBe("前文。后文。");
  });

  it("防误伤：普通回答 / 中后段普通 JSON / 无 phases / 空 items 均不命中", () => {
    expect(stripPlanDraftBlocks("我为你制定了四周计划。")).toBeNull();
    expect(stripPlanDraftBlocks('草案数据：{"name":"课程"} 请查收')).toBeNull();
    expect(stripPlanDraftBlocks('{"phases":[]}')).toBeNull();
    expect(
      stripPlanDraftBlocks('{"phases":[{"title":"一","items":[]}]}'),
    ).toBeNull();
    // 用户主动要求输出 JSON 的正常回答（普通代码块）原样保留。
    const normalJsonBlock = '配置如下：\n```json\n{"key":"value"}\n```';
    expect(stripPlanDraftBlocks(normalJsonBlock)).toBeNull();
  });

  it("流中断的半截 JSON（未闭合）：静态判定不命中，原文保留（诚实呈现）", () => {
    expect(stripPlanDraftBlocks('我先确认目标。{"phases":[{')).toBeNull();
  });
});

describe("planDraftStreamingView（流式视图，位置无关）", () => {
  it("中文打字中（无 JSON）→ 原文渲染", () => {
    expect(planDraftStreamingView("我先确认目标，再")).toEqual({
      kind: "text",
      text: "我先确认目标，再",
    });
  });

  it("中文出现后 JSON 开始产出（未闭合）→ 截断到 JSON 起点，只见中文", () => {
    expect(
      planDraftStreamingView('我先确认目标。{"phases":[{"title":"第一'),
    ).toEqual({ kind: "text", text: "我先确认目标。" });
  });

  it("JSON 打字中且前部无文本 → 占位", () => {
    expect(planDraftStreamingView('{"phases":[{"tit')).toEqual({
      kind: "pending",
    });
  });

  it("JSON 闭合且命中、后续中文打字中 → 剥离 JSON 渲染后续中文", () => {
    expect(planDraftStreamingView(`${draftJson(2)}已按目标生成`)).toEqual({
      kind: "text",
      text: "已按目标生成",
    });
    expect(
      planDraftStreamingView(`我先确认。${draftJson(2)}已按目标生成`),
    ).toEqual({ kind: "text", text: "我先确认。已按目标生成" });
  });

  it("JSON 闭合且命中、尚无后续文本 → 占位（流结束由折叠块兜底）", () => {
    expect(planDraftStreamingView(draftJson())).toEqual({ kind: "pending" });
  });

  it("围栏开放中 → 截断到围栏起点", () => {
    expect(planDraftStreamingView('草案如下：\n```json\n{"phases":[')).toEqual({
      kind: "text",
      text: "草案如下：",
    });
  });

  it("闭合但非草案形状（用户要的普通 JSON）→ 恢复显示原文", () => {
    expect(planDraftStreamingView('配置：{"key":"value"}')).toEqual({
      kind: "text",
      text: '配置：{"key":"value"}',
    });
  });
});
