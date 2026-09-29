import { describe, expect, it } from "vitest";
import {
  isJsonObjectPrefix,
  matchPlanDraftJson,
} from "@/features/chat/planDraftJson";

const DRAFT = `{"goal_id":"90000000-0000-4000-8000-000000000001","phases":[{"title":"第一阶段","items":[{"action_type":"STUDY_RECORD","content":"精读第 1 讲","estimated_minutes":60,"reason":"建立基础","record_id":"a0000000-0000-4000-8000-000000000001","scheduled_date":"2026-09-29"}]}]}`;

describe("matchPlanDraftJson（计划草案 JSON 正文兜底判定）", () => {
  it("纯草案 JSON 命中：返回剥围栏原文与项数", () => {
    const match = matchPlanDraftJson(`  ${DRAFT}  `);
    expect(match).not.toBeNull();
    expect(match?.itemCount).toBe(1);
    expect(match?.raw).toBe(DRAFT);
  });

  it("```json 围栏包裹命中", () => {
    const match = matchPlanDraftJson("```json\n" + DRAFT + "\n```");
    expect(match).not.toBeNull();
    expect(match?.itemCount).toBe(1);
  });

  it("多阶段项数合计", () => {
    const two = JSON.stringify({
      phases: [
        { title: "一", items: [{}, {}] },
        { title: "二", items: [{}] },
      ],
    });
    expect(matchPlanDraftJson(two)?.itemCount).toBe(3);
  });

  it("普通中文回答不命中", () => {
    expect(
      matchPlanDraftJson("我为你制定了一份四周计划：第一阶段……"),
    ).toBeNull();
  });

  it("含 JSON 片段的正常回答不命中（JSON 不是正文整体）", () => {
    expect(matchPlanDraftJson(`好的，草案如下：\n${DRAFT}`)).toBeNull();
  });

  it("非草案形状的合法 JSON 不命中（无 phases / 空 items）", () => {
    expect(matchPlanDraftJson('{"name":"课程"}')).toBeNull();
    expect(matchPlanDraftJson('{"phases":[]}')).toBeNull();
    expect(
      matchPlanDraftJson('{"phases":[{"title":"一","items":[]}]}'),
    ).toBeNull();
  });

  it("截断 JSON 不命中（不完整正文交回正常渲染）", () => {
    expect(matchPlanDraftJson(DRAFT.slice(0, 40))).toBeNull();
  });
});

describe("isJsonObjectPrefix（流式占位判定）", () => {
  it("以 { 或 ```json 起势命中", () => {
    expect(isJsonObjectPrefix('{"phases":[')).toBe(true);
    expect(isJsonObjectPrefix("```json\n{}")).toBe(true);
  });

  it("中文起势不命中（正常回答直接走 Streamdown）", () => {
    expect(isJsonObjectPrefix("好的，计划如下：")).toBe(false);
  });
});
