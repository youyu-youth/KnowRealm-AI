/**
 * 计划草案 JSON 正文剥离（工单 02 真机验收修复，二轮）。
 *
 * 真机观察：模型（提示词禁令之后仍会）在构造 confirm_plan 的超长参数时，
 * 先把草案 JSON 完整输出到正文、再输出中文复述——前导 JSON + 中文复述的
 * 混合形态。本模块做确定性前导剥离：字符串感知的括号配平找到顶层对象
 * 边界，解析成功且形如草案（顶层非空 phases[].items）即剥掉前导 JSON，
 * 只保留剩余中文；剩余为空（正文整体即 JSON）时由折叠块兜底呈现。
 */

/** 计数顶层对象包含的计划项（phases[].items 长度合计）；非草案形状返回 null。 */
function countPlanItems(parsed: unknown): number | null {
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
  return itemCount;
}

/**
 * 字符串/转义感知地找顶层 JSON 对象的闭括号结束位置（含该 `}` 的下一字符
 * 索引）；未闭合（流式进行中）返回 null。文本必须以 `{` 开头。
 */
function findTopLevelObjectEnd(text: string): number | null {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return index + 1;
      }
    }
  }
  return null;
}

/** 解析候选 JSON 并校验草案形状；命中返回计划项数，否则 null。 */
function parsePlanDraft(candidate: string): number | null {
  try {
    return countPlanItems(JSON.parse(candidate));
  } catch {
    return null;
  }
}

export type PlanDraftSplit = {
  /** 前导草案 JSON 原文（剩余为空时的折叠块展示用）。 */
  json: string;
  /** 计划项总数（phases[].items 长度合计）。 */
  itemCount: number;
  /** JSON 之后的剩余文本（trim；正文整体即 JSON 时为空串）。 */
  rest: string;
};

/**
 * 前导草案 JSON 剥离：正文以草案 JSON 开头（裸 `{` 或 ```json 围栏，其后可
 * 跟任意中文）即命中。整体是普通 JSON / JSON 出现在正文中后段 / 非草案
 * 形状（无 phases）均不命中，交回正常渲染。
 */
export function splitPlanDraftJson(text: string): PlanDraftSplit | null {
  const trimmed = text.trim();
  let jsonCandidate: string | null = null;
  let rest = "";
  if (trimmed.startsWith("```")) {
    const closing = trimmed.indexOf("```", 3);
    if (closing === -1) {
      return null;
    }
    jsonCandidate = trimmed
      .slice(3, closing)
      .replace(/^json\s*/, "")
      .trim();
    rest = trimmed.slice(closing + 3).trim();
  } else if (trimmed.startsWith("{")) {
    const end = findTopLevelObjectEnd(trimmed);
    if (end === null) {
      return null;
    }
    jsonCandidate = trimmed.slice(0, end);
    rest = trimmed.slice(end).trim();
  } else {
    return null;
  }
  const itemCount = parsePlanDraft(jsonCandidate);
  if (itemCount === null) {
    return null;
  }
  return { json: jsonCandidate, itemCount, rest };
}

/** 兼容整体形态：正文整体（或整体围栏包裹）是草案 JSON 时的折叠块输入。 */
export function matchPlanDraftJson(text: string): {
  raw: string;
  itemCount: number;
} | null {
  const split = splitPlanDraftJson(text);
  if (split === null || split.rest !== "") {
    return null;
  }
  return { raw: split.json, itemCount: split.itemCount };
}

export type StreamingTextView =
  /** 前导 JSON 仍在流式产出（未闭合/围栏未闭合/刚闭合等待后续文本）。 */
  | { kind: "pending" }
  /** 可渲染的正文文本（剥离后的剩余中文，或判定未命中的原文回放）。 */
  | { kind: "text"; text: string };

/**
 * 流式视图：前导 JSON 流式期间收敛为占位态，闭合后把剩余文本交给正常
 * 流式渲染（中文打字可见）；JSON 刚闭合尚无剩余文本时保持占位（流结束后
 * 由静态分支的折叠块兜底，避免闪现）。
 */
export function planDraftStreamingView(text: string): StreamingTextView {
  const trimmed = text.trim();
  if (trimmed.startsWith("```") && !trimmed.slice(3).includes("```")) {
    return { kind: "pending" };
  }
  if (trimmed.startsWith("{") && findTopLevelObjectEnd(trimmed) === null) {
    return { kind: "pending" };
  }
  const split = splitPlanDraftJson(trimmed);
  if (split === null) {
    return { kind: "text", text };
  }
  if (split.rest === "") {
    return { kind: "pending" };
  }
  return { kind: "text", text: split.rest };
}
