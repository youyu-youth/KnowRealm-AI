/**
 * 计划草案 JSON 正文剥离（工单 02 真机验收修复，三轮定稿）。
 *
 * 真机三轮观察：模型（提示词禁令无效）在构造 confirm_plan 的超长参数时把
 * 参数 JSON 混入正文流，**位置不固定**——JSON 独占正文 / JSON 在前中文在
 * 后 / 中文在前 JSON 在后都出现过。因此本模块按**形状**而非**位置**锚定：
 * 全文扫描所有平衡闭合的顶层 `{...}` 块（含 ```json 围栏），命中草案专属
 * 形状（解析成功且顶层非空 phases[].items）即从渲染文本中移除，剩余中文
 * 照常渲染；防误伤完全由形状保证（正常回答里的普通 JSON 顶层不会是
 * phases 草案结构）。流式期间：已闭合命中段实时移除；未闭合的开放段从其
 * 起点截断不透出（闭合后再判定，非草案形状则恢复显示）。
 */

/** 计数草案计划项（phases[].items 长度合计）；非草案形状返回 null。 */
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

/** 候选 JSON 解析 + 草案形状校验；命中返回计划项数，否则 null。 */
function parsePlanDraft(candidate: string): number | null {
  try {
    return countPlanItems(JSON.parse(candidate));
  } catch {
    return null;
  }
}

/**
 * 从 `text[from]`（必须是 `{`）出发做字符串/转义感知的括号配平，返回闭括号
 * 的下一字符索引；未闭合返回 null。
 */
function matchObject(text: string, from: number): number | null {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = from; index < text.length; index += 1) {
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

/** 顶层 JSON 块扫描结果：平衡块区间 + 首个未闭合开放块的起点。 */
type BlockScan = {
  blocks: { start: number; end: number }[];
  openStart: number | null;
};

/** 扫描文本中所有顶层 `{...}` 平衡块（字符串感知；字符串内的花括号不参与配平）。 */
function scanTopLevelBlocks(text: string): BlockScan {
  const blocks: { start: number; end: number }[] = [];
  let index = 0;
  while (index < text.length) {
    if (text[index] === "{") {
      const end = matchObject(text, index);
      if (end === null) {
        return { blocks, openStart: index };
      }
      blocks.push({ start: index, end });
      index = end;
    } else {
      index += 1;
    }
  }
  return { blocks, openStart: null };
}

/** 围栏块区间（含 ``` 标记）：已闭合围栏整体区间 + 未闭合围栏起点。 */
type FenceScan = BlockScan;

/** 扫描 ``` 围栏块（```json 或裸 ```，含标记整段）；未闭合围栏记 openStart。 */
function scanFences(text: string): FenceScan {
  const blocks: { start: number; end: number }[] = [];
  let index = text.indexOf("```");
  while (index !== -1) {
    const closing = text.indexOf("```", index + 3);
    if (closing === -1) {
      return { blocks, openStart: index };
    }
    blocks.push({ start: index, end: closing + 3 });
    index = text.indexOf("```", closing + 3);
  }
  return { blocks, openStart: null };
}

/** 围栏内容 JSON（剥 ```json 语言标记行）。 */
function fenceCandidate(
  text: string,
  block: { start: number; end: number },
): string {
  return text
    .slice(block.start + 3, block.end - 3)
    .replace(/^json[^\n]*\n/, "")
    .trim();
}

/** 命中的移除段：区间 + 草案 JSON 原文与项数。 */
type Removal = { start: number; end: number; json: string; itemCount: number };

/**
 * 收集全部应移除的草案段（位置无关）：围栏内 JSON 命中则整段围栏移除；
 * 裸顶层块命中则移除该块。openFrom 非 null 时给出首个开放段（围栏或裸块）
 * 起点，供流式截断。
 */
function collectRemovals(text: string): {
  removals: Removal[];
  openFrom: number | null;
} {
  const removals: Removal[] = [];
  const openStarts: number[] = [];
  const fences = scanFences(text);
  if (fences.openStart !== null) {
    openStarts.push(fences.openStart);
  }
  for (const fence of fences.blocks) {
    const candidate = fenceCandidate(text, fence);
    const itemCount = parsePlanDraft(candidate);
    if (itemCount !== null) {
      removals.push({ ...fence, json: candidate, itemCount });
    }
  }
  // 裸块只在围栏外扫描：围栏区间内的块不重复判定（围栏不命中时其内容原样保留）。
  const scan = scanTopLevelBlocks(text);
  if (scan.openStart !== null) {
    openStarts.push(scan.openStart);
  }
  for (const block of scan.blocks) {
    const insideFence = fences.blocks.some(
      (fence) => block.start >= fence.start && block.end <= fence.end,
    );
    if (insideFence) {
      continue;
    }
    const candidate = text.slice(block.start, block.end);
    const itemCount = parsePlanDraft(candidate);
    if (itemCount !== null) {
      removals.push({ ...block, json: candidate, itemCount });
    }
  }
  removals.sort((a, b) => a.start - b.start);
  const openFrom = openStarts.length > 0 ? Math.min(...openStarts) : null;
  return { removals, openFrom };
}

/** 按移除段/截断点拼接剩余文本（移除段外扩吞掉紧邻空白，避免残留空行）。 */
function remainder(
  text: string,
  removals: Removal[],
  truncateFrom: number | null,
): string {
  const cuts: { start: number; end: number }[] = removals.map((removal) => ({
    start: removal.start,
    end: removal.end,
  }));
  if (truncateFrom !== null) {
    cuts.push({ start: truncateFrom, end: text.length });
  }
  let result = "";
  let cursor = 0;
  for (const cut of cuts) {
    result += text.slice(cursor, cut.start);
    cursor = Math.max(cursor, cut.end);
  }
  result += text.slice(cursor);
  return result
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export type PlanDraftStripped = {
  /** 移除全部草案段后的剩余文本（trim；正文整体即草案时空串）。 */
  rest: string;
  /** 命中的草案段（正常至多一个；折叠块展示与摘要用）。 */
  blocks: { json: string; itemCount: number }[];
};

/**
 * 位置无关的草案剥离：移除正文中所有草案形状的 JSON 段（围栏或裸块，任意
 * 位置）；无命中返回 null（原文照常渲染，防误伤由形状保证）。
 */
export function stripPlanDraftBlocks(text: string): PlanDraftStripped | null {
  const { removals, openFrom } = collectRemovals(text);
  if (removals.length === 0) {
    return null;
  }
  return {
    rest: remainder(text, removals, openFrom),
    blocks: removals.map(({ json, itemCount }) => ({ json, itemCount })),
  };
}

export type StreamingTextView =
  /** 前部文本被全部移除/截断（JSON 产出中），显示占位。 */
  | { kind: "pending" }
  /** 可渲染的正文文本（移除草案段与开放段截断之后）。 */
  | { kind: "text"; text: string };

/**
 * 流式视图（位置无关）：已闭合命中段实时移除；未闭合的开放段（围栏或裸
 * `{`）从其起点截断——JSON 打字期间不透出；闭合且命中则保持移除，闭合但
 * 非草案形状（罕见）在下一次计算中自然恢复显示。
 */
export function planDraftStreamingView(text: string): StreamingTextView {
  const { removals, openFrom } = collectRemovals(text);
  if (removals.length === 0 && openFrom === null) {
    // 无命中无开放段：原文照常渲染（不经过空白压缩，保持正常回答原样）。
    return { kind: "text", text };
  }
  const visible = remainder(text, removals, openFrom);
  if (visible !== "") {
    return { kind: "text", text: visible };
  }
  return { kind: "pending" };
}
