import type {
  KnowledgePointOut,
  QuizOut,
  TodoOut,
} from "@/features/records/api/types";

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

export type QuizExportLabels = {
  assetTitle: string;
  questionTypeLabel: string;
  stemLabel: string;
  difficultyLabel: string;
  optionsLabel: string;
  userAnswerLabel: string;
  resultLabel: string;
  correctAnswerLabel: string;
  referenceAnswerLabel: string;
  explanationLabel: string;
  pendingSelfAssessment: string;
  questionTypes: Record<QuizOut["question_type"], string>;
  difficulties: Record<QuizOut["difficulty"], string>;
  results: Record<NonNullable<QuizOut["answer_result"]>, string>;
};

/**
 * 纯文本字段转义：井号、星号、下划线、反引号、方括号与原始 HTML 不改变文档结构，
 * 反斜杠先行转义保证用户输入的反斜杠不会吞掉后续转义；渲染后的可见文本不变。
 */
function escapePlainText(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .replace(/([\\`*_#&<>[\]|])/g, "\\$1")
    .replace(/^(\s*)([-+])(?=\s)/gm, "$1\\$2")
    .replace(/^(\s*)(\d+)([.)])(?=\s)/gm, "$1$2\\$3")
    .replace(/^(\s*)([-=~]{3,})(\s*)$/gm, "$1\\$2$3")
    .replace(/^ {4}/gm, "&#32;   ")
    .replace(/^( {0,3})\t/gm, "$1&#9;");
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

/** 只保留当前 ACTIVE 习题，沿用接口与页面顺序。 */
export function selectActiveQuizzes(items: readonly QuizOut[]): QuizOut[] {
  return items.filter((item) => item.generation_status === "ACTIVE");
}

function objectiveAnswerText(item: QuizOut, index: number): string {
  const option = item.options[index];
  return item.question_type === "TRUE_FALSE"
    ? option
    : `${String.fromCharCode(65 + index)}. ${option}`;
}

function quizAnswerText(
  item: QuizOut,
  answer: QuizOut["user_answer"] | QuizOut["correct_answer"],
): string | null {
  if (typeof answer === "number") return objectiveAnswerText(item, answer);
  if (typeof answer === "string") return answer;
  if (!Array.isArray(answer)) return null;
  if (answer.every((value) => typeof value === "number")) {
    return answer.map((value) => objectiveAnswerText(item, value)).join("、");
  }
  if (answer.every((value) => typeof value === "string")) {
    return answer
      .map((value, index) => `第 ${index + 1} 空：${value}`)
      .join("；");
  }
  if (
    answer.every(
      (value) =>
        Array.isArray(value) &&
        value.every((alternative) => typeof alternative === "string"),
    )
  ) {
    return answer
      .map((value, index) => `第 ${index + 1} 空：${value.join(" / ")}`)
      .join("；");
  }
  return null;
}

function labeledText(label: string, text: string): string[] {
  return [`**${escapePlainText(label)}**`, escapePlainText(text)];
}

export function serializeQuizMarkdown(
  recordTitle: string,
  items: readonly QuizOut[],
  labels: QuizExportLabels,
): string {
  const blocks = [
    `# ${escapePlainText(recordTitle)}`,
    `## ${escapePlainText(labels.assetTitle)}`,
  ];
  items.forEach((item, index) => {
    blocks.push(`### ${index + 1}`);
    blocks.push(
      [
        `- ${escapePlainText(labels.questionTypeLabel)}：${escapePlainText(labels.questionTypes[item.question_type])}`,
        `- ${escapePlainText(labels.difficultyLabel)}：${escapePlainText(labels.difficulties[item.difficulty])}`,
      ].join("\n"),
    );
    blocks.push(...labeledText(labels.stemLabel, item.stem));
    if (item.options.length) {
      blocks.push(`**${escapePlainText(labels.optionsLabel)}**`);
      blocks.push(
        item.options
          .map(
            (_option, optionIndex) =>
              `- ${escapePlainText(objectiveAnswerText(item, optionIndex))}`,
          )
          .join("\n"),
      );
    }
    if (item.answered_at === null) return;

    if (item.question_type === "SHORT_ANSWER") {
      if (
        typeof item.user_answer !== "string" ||
        typeof item.correct_answer !== "string" ||
        item.explanation === null
      ) {
        return;
      }
      blocks.push(
        ...labeledText(labels.userAnswerLabel, item.user_answer),
        ...labeledText(labels.referenceAnswerLabel, item.correct_answer),
        ...labeledText(labels.explanationLabel, item.explanation),
        ...labeledText(
          labels.resultLabel,
          item.answer_result === null || item.answer_result === undefined
            ? labels.pendingSelfAssessment
            : labels.results[item.answer_result],
        ),
      );
      return;
    }

    const userAnswer = quizAnswerText(item, item.user_answer);
    const correctAnswer = quizAnswerText(item, item.correct_answer);
    if (
      !userAnswer ||
      !correctAnswer ||
      !item.answer_result ||
      item.explanation === null
    ) {
      return;
    }

    blocks.push(
      ...labeledText(labels.userAnswerLabel, userAnswer),
      ...labeledText(labels.resultLabel, labels.results[item.answer_result]),
      ...labeledText(labels.correctAnswerLabel, correctAnswer),
      ...labeledText(labels.explanationLabel, item.explanation),
    );
  });
  return assembleDocument(blocks);
}

/** 正式 Todo 是 ACTIVE AI 项，以及 generation_status 为 null 的手工/被接管项。 */
export function selectFormalTodos(items: readonly TodoOut[]): TodoOut[] {
  return items
    .filter(
      (item) =>
        item.generation_status === "ACTIVE" || item.generation_status === null,
    )
    .slice()
    .sort((left, right) => left.sort_order - right.sort_order);
}

export function serializeTodoMarkdown(
  recordTitle: string,
  items: readonly TodoOut[],
  assetTitle: string,
): string {
  return assembleDocument([
    `# ${escapePlainText(recordTitle)}`,
    `## ${escapePlainText(assetTitle)}`,
    items
      .map(
        (item) =>
          `- [${item.status === "DONE" ? "x" : " "}] ${escapePlainText(item.content).replace(/\n/g, "\n  ")}`,
      )
      .join("\n"),
  ]);
}

/** 复用单项文档正文，按调用方给定的白名单顺序合并为一个 Record 文档。 */
export function serializeAggregateMarkdown(
  recordTitle: string,
  assetDocuments: readonly (string | null)[],
): string | null {
  const title = `# ${escapePlainText(recordTitle)}`;
  const prefix = `${title}\n\n`;
  const assets = assetDocuments
    .filter((document): document is string => document !== null)
    .map((document) => {
      if (!document.startsWith(prefix) || !document.endsWith("\n")) {
        throw new Error("聚合导出的单项 Markdown 格式无效");
      }
      return document.slice(prefix.length, -1);
    });
  return assets.length ? assembleDocument([title, ...assets]) : null;
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
