// 对话转知识点 V1：保存对话框的详情预填草稿（完整正文）。
// 规则确定性提取（非 LLM）：先剥离计划草案 JSON 段（与渲染路径
// stripPlanDraftBlocks 对齐），再保留全部段落——文本段去 markdown 标记与
// [n] 引用角标，代码块去围栏标记、内容原样——拼接后截断至后端 2000 字
// 上限。草稿仅供用户编辑确认。
import { stripPlanDraftBlocks } from "./planDraftJson";

export const SAVE_DRAFT_MAX_LENGTH = 2000;

/** 去行内 markdown 标记：标题/加粗/斜体/行内代码/链接（保留文字）/列表/引用。 */
function stripInlineMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\|/g, "")
    .trim();
}

export function buildSaveDraft(content: string): string {
  const stripped = stripPlanDraftBlocks(content);
  const blocks = (stripped?.rest ?? content)
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const parts: string[] = [];
  let inFence = false;
  for (const block of blocks) {
    if (inFence) {
      // 围栏续块（代码块内部空行把块切开）：内容原样，闭合标记行去掉。
      const closed = block.endsWith("```");
      parts.push(closed ? block.replace(/```[^\n]*$/, "").trim() : block);
      inFence = !closed;
      continue;
    }
    // 多行且以 ``` 开头才是围栏块；单行围栏（罕见）走文本路径防误吞后续段落。
    if (block.startsWith("```") && block.includes("\n")) {
      let inner = block.replace(/^```[^\n]*\n?/, "");
      const closed = inner.endsWith("```");
      if (closed) {
        inner = inner.replace(/\n?```[^\n]*$/, "");
      }
      inFence = !closed;
      parts.push(inner.trim());
      continue;
    }
    const text = stripInlineMarkdown(block.replace(/\s*\[\d{1,3}\]/g, ""));
    if (text !== "") {
      parts.push(text);
    }
  }
  return parts
    .filter(Boolean)
    .join("\n\n")
    .slice(0, SAVE_DRAFT_MAX_LENGTH)
    .trimEnd();
}
