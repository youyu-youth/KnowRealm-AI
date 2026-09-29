/**
 * 计划草案 JSON 正文兜底（工单 02 真机验收修复）。
 *
 * 模型偶发把 confirm_plan 的工具参数（草案 JSON）粘贴到回复正文而非
 * （或先于）工具调用——提示词层已禁止（chat prompt v20/v21），本模块是
 * 前端确定性兜底：识别「正文整体是计划草案 JSON」的专属形状（顶层非空
 * phases[].items），命中时消息列表以折叠块呈现而非裸 JSON 裸奔。
 */

/** 剥离包裹整段正文的 ```json 围栏；非围栏包裹时原样返回（已 trim）。 */
function stripJsonFence(text: string): string {
  const trimmed = text.trim();
  const fenced = /^```(?:json)?\s*\n([\s\S]*?)\n?\s*```$/m.exec(trimmed);
  return fenced !== null ? fenced[1].trim() : trimmed;
}

export type PlanDraftJsonMatch = {
  /** 剥围栏后的原始 JSON 文本（折叠块展开时展示）。 */
  raw: string;
  /** 计划项总数（phases[].items 长度合计，摘要行用）。 */
  itemCount: number;
};

/** 正文是否为计划草案 JSON：整体可解析、顶层含非空 phases[].items。 */
export function matchPlanDraftJson(text: string): PlanDraftJsonMatch | null {
  const raw = stripJsonFence(text);
  if (!raw.startsWith("{")) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) {
    return null;
  }
  const phases = (parsed as Record<string, unknown>)["phases"];
  if (!Array.isArray(phases) || phases.length === 0) {
    return null;
  }
  let itemCount = 0;
  for (const phase of phases) {
    if (typeof phase !== "object" || phase === null) {
      return null;
    }
    const items = (phase as Record<string, unknown>)["items"];
    if (!Array.isArray(items) || items.length === 0) {
      return null;
    }
    itemCount += items.length;
  }
  return { raw, itemCount };
}

/**
 * 流式占位判定：文本已呈现「JSON 正文」起势（去围栏标记后以 `{` 开头）。
 * 流式过程无法完整解析，用起势判定先收敛为占位态，流结束后由
 * matchPlanDraftJson 做完整判定（不命中则恢复 Streamdown 正常渲染）。
 */
export function isJsonObjectPrefix(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("```json");
}
