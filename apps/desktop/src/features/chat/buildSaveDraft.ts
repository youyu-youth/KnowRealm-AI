// 对话转知识点 V1：保存对话框的详情预填草稿（聚焦摘要）。
// 规则确定性提取（非 LLM）：首个文本段去 markdown 标记 + 带 [n] 引用角的句子
// 去角标去重，拼接后截断至后端 2000 字上限。草稿仅供用户编辑确认。
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

/** 提取带 [n] 引用角的句子：去角标、去 markdown 标记、按原文顺序去重。 */
function citedSentences(content: string): string[] {
  const sentences = content
    .split(/(?<=[。！？!?\n])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const result: string[] = [];
  for (const sentence of sentences) {
    if (!/\[\d{1,3}\]/.test(sentence)) continue;
    const clean = stripInlineMarkdown(sentence.replace(/\s*\[\d{1,3}\]/g, ""));
    if (clean === "" || seen.has(clean)) continue;
    seen.add(clean);
    result.push(clean);
  }
  return result;
}

export function buildSaveDraft(content: string): string {
  const blocks = content
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const firstTextBlock = blocks.find((block) => !block.startsWith("```"));
  const firstParagraph = firstTextBlock
    ? stripInlineMarkdown(firstTextBlock)
    : "";
  const parts = [firstParagraph, ...citedSentences(content)].filter(Boolean);
  return parts.join("\n\n").slice(0, SAVE_DRAFT_MAX_LENGTH).trimEnd();
}
