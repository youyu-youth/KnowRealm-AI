import type { KnowledgePointOut } from "@/features/records/api/types";

export type SummaryExportSnapshot = {
  topic: string;
  abstract: string;
  sections: readonly {
    heading: string;
    points: readonly string[];
  }[];
};

export type SummaryExportLabels = {
  assetTitle: string;
  topicLabel: string;
  abstractLabel: string;
};

export type KnowledgePointExportItem = {
  name: string;
  detail: string;
  importance: number;
  tags: readonly string[];
};

export type KnowledgePointExportLabels = {
  assetTitle: string;
  importanceLabel: string;
  tagsLabel: string;
};

/**
 * 纯文本字段转义：井号、星号、下划线、反引号、方括号与原始 HTML 不改变文档结构，
 * 反斜杠先行转义保证用户输入的反斜杠不会吞掉后续转义；渲染后的可见文本不变。
 */
function escapePlainText(text: string): string {
  return text.replace(/\r\n?/g, "\n").replace(/([\\`*_#&<>[\]])/g, "\\$1");
}

/** 区块之间一个空行，文件末尾一个换行。 */
function assembleDocument(blocks: readonly string[]): string {
  return `${blocks.join("\n\n")}\n`;
}

export function serializeSummaryMarkdown(
  recordTitle: string,
  snapshot: SummaryExportSnapshot,
  labels: SummaryExportLabels,
): string {
  const blocks = [
    `# ${escapePlainText(recordTitle)}`,
    `## ${escapePlainText(labels.assetTitle)}`,
    `**${escapePlainText(labels.topicLabel)}**：${escapePlainText(snapshot.topic)}`,
    `**${escapePlainText(labels.abstractLabel)}**：${escapePlainText(snapshot.abstract)}`,
  ];
  for (const section of snapshot.sections) {
    blocks.push(`### ${escapePlainText(section.heading)}`);
    blocks.push(
      section.points.map((point) => `- ${escapePlainText(point)}`).join("\n"),
    );
  }
  return assembleDocument(blocks);
}

/** 只保留未删除的 ACTIVE 项，排除 DRAFT 与 SUPERSEDED，沿用接口顺序。 */
export function selectActiveKnowledgePoints(
  items: readonly KnowledgePointOut[],
): KnowledgePointExportItem[] {
  return items
    .filter((item) => item.generation_status === "ACTIVE")
    .map((item) => ({
      name: item.name,
      detail: item.detail,
      importance: item.importance,
      tags: item.tags.filter((tag) => tag !== ""),
    }));
}

export function serializeKnowledgePointsMarkdown(
  recordTitle: string,
  items: readonly KnowledgePointExportItem[],
  labels: KnowledgePointExportLabels,
): string {
  const blocks = [
    `# ${escapePlainText(recordTitle)}`,
    `## ${escapePlainText(labels.assetTitle)}`,
  ];
  for (const item of items) {
    blocks.push(`### ${escapePlainText(item.name)}`);
    blocks.push(escapePlainText(item.detail));
    const fields = [
      `- ${escapePlainText(labels.importanceLabel)}：${item.importance}/5`,
    ];
    if (item.tags.length) {
      fields.push(
        `- ${escapePlainText(labels.tagsLabel)}：${item.tags
          .map((tag) => escapePlainText(tag))
          .join("、")}`,
      );
    }
    blocks.push(fields.join("\n"));
  }
  return assembleDocument(blocks);
}

const WINDOWS_RESERVED_NAMES = new Set([
  "CON",
  "PRN",
  "AUX",
  "NUL",
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
]);

/**
 * 单项导出默认文件名：`{Record展示标题}-{资产类型}.md`。
 * 过滤 Windows 非法字符、控制字符、尾部点/空格并避开设备保留名；
 * 清理后为空或命中保留名时回退未命名学习记录。
 */
export function buildExportFileName(
  recordTitle: string,
  assetLabel: string,
  untitledFallback: string,
): string {
  const clean = (value: string) =>
    value
      .replace(/[<>:"/\\|?*]/g, "")
      // Windows 文件名不允许控制字符，这里正是要把它们过滤掉
      // eslint-disable-next-line no-control-regex
      .replace(/[\u0000-\u001F\u007F]/g, "")
      .replace(/[. ]+$/u, "");
  const titlePart = clean(recordTitle.trim()) || clean(untitledFallback);
  const labelPart = clean(assetLabel.trim());
  let stem = labelPart ? `${titlePart}-${labelPart}` : titlePart;
  if (!stem || WINDOWS_RESERVED_NAMES.has(stem.toUpperCase())) {
    stem = clean(untitledFallback);
  }
  return `${stem}.md`;
}
