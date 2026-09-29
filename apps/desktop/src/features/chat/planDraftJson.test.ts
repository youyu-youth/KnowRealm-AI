import { describe, expect, it } from "vitest";
import {
  matchPlanDraftJson,
  planDraftStreamingView,
  splitPlanDraftJson,
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

describe("splitPlanDraftJson（前导草案 JSON 剥离）", () => {
  it("前导 JSON + 中文复述的混合形态：剥离 JSON，剩余中文", () => {
    const text = `${draftJson(2)}\n已按目标生成草案，共 5 个阶段，请过目。`;
    const split = splitPlanDraftJson(text);
    expect(split).not.toBeNull();
    expect(split?.itemCount).toBe(2);
    expect(split?.rest).toBe("已按目标生成草案，共 5 个阶段，请过目。");
    expect(split?.json).toBe(draftJson(2));
  });

  it("```json 围栏前导 + 中文：同样剥离", () => {
    const text = "```json\n" + draftJson(1) + "\n```\n以上是草案安排。";
    const split = splitPlanDraftJson(text);
    expect(split).not.toBeNull();
    expect(split?.rest).toBe("以上是草案安排。");
  });

  it("正文整体是草案 JSON：命中且 rest 为空（折叠块场景）", () => {
    const split = splitPlanDraftJson(`  ${draftJson(3)}  `);
    expect(split).not.toBeNull();
    expect(split?.rest).toBe("");
    expect(split?.itemCount).toBe(3);
  });

  it("多阶段项数合计", () => {
    const two = JSON.stringify({
      phases: [
        { title: "一", items: [{}, {}] },
        { title: "二", items: [{}] },
      ],
    });
    expect(splitPlanDraftJson(two)?.itemCount).toBe(3);
  });

  it("JSON 内含转义引号与嵌套花括号不误判边界", () => {
    const tricky = JSON.stringify({
      phases: [{ title: '含"}"与\\', items: [{ note: "a{b}c" }] }],
    });
    const split = splitPlanDraftJson(`${tricky}后续中文`);
    expect(split).not.toBeNull();
    expect(split?.rest).toBe("后续中文");
  });

  it("普通中文回答 / JSON 出现在中后段 / 非草案形状 JSON 均不命中", () => {
    expect(splitPlanDraftJson("我为你制定了四周计划。")).toBeNull();
    expect(splitPlanDraftJson(`草案如下：\n${draftJson()}`)).toBeNull();
    expect(splitPlanDraftJson('{"name":"课程"}')).toBeNull();
    expect(splitPlanDraftJson('{"phases":[]}')).toBeNull();
    expect(
      splitPlanDraftJson('{"phases":[{"title":"一","items":[]}]}后续'),
    ).toBeNull();
  });

  it("前导 { 开头但非合法 JSON（罕见形态）：不命中，回放原文", () => {
    expect(splitPlanDraftJson("{ 这不是 JSON 结构化内容")).toBeNull();
  });
});

describe("matchPlanDraftJson（整体形态兼容）", () => {
  it("整体草案 JSON 命中；混合形态不命中（走 split 的 rest 渲染）", () => {
    expect(matchPlanDraftJson(draftJson())?.itemCount).toBe(1);
    expect(matchPlanDraftJson(`${draftJson()}后续`)).toBeNull();
  });
});

describe("planDraftStreamingView（流式视图）", () => {
  it("前导 JSON 未闭合 → 占位", () => {
    expect(planDraftStreamingView('{"phases":[{"tit')).toEqual({
      kind: "pending",
    });
  });

  it("围栏未闭合 → 占位", () => {
    expect(planDraftStreamingView("```json\n{}")).toEqual({ kind: "pending" });
  });

  it("JSON 刚闭合尚无后续文本 → 保持占位（防闪现，流结束由折叠块兜底）", () => {
    expect(planDraftStreamingView(draftJson())).toEqual({ kind: "pending" });
  });

  it("JSON 闭合后中文打字中 → 渲染剩余中文", () => {
    expect(planDraftStreamingView(`${draftJson()}已按目标生成`)).toEqual({
      kind: "text",
      text: "已按目标生成",
    });
  });

  it("中文起势（正常回答）→ 原文渲染", () => {
    expect(planDraftStreamingView("好的，计划如下：")).toEqual({
      kind: "text",
      text: "好的，计划如下：",
    });
  });
});
