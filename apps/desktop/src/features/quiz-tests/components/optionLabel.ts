import type { QuizTestItem } from "@/features/quiz-tests/api/types";

/** 选项显示文本（判断题不加 A/B 前缀）；作答控件与批改块共用 */
export function optionLabel(item: QuizTestItem, index: number): string {
  const option = item.options[index] ?? "";
  return item.question_type === "TRUE_FALSE"
    ? option
    : `${String.fromCharCode(65 + index)}. ${option}`;
}
