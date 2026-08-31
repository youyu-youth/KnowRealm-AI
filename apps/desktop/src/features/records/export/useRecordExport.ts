import type { TFunction } from "i18next";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { recordApi } from "@/features/records/api/records";
import {
  buildExportFileName,
  selectActiveKnowledgePoints,
  selectActiveQuizzes,
  selectFormalTodos,
  serializeAggregateMarkdown,
  serializeKnowledgePointsMarkdown,
  serializeQuizMarkdown,
  serializeSummaryMarkdown,
  serializeTodoMarkdown,
} from "@/features/records/export/serializers";
import type { QuizExportLabels } from "@/features/records/export/serializers";
import {
  chooseMarkdownSavePath,
  openExportedFile,
  writeMarkdownFile,
} from "@/services/tauri/learningAssetExport";

export type RecordExportState =
  | { phase: "idle" }
  | { phase: "exporting" }
  | { phase: "unavailable"; message: string }
  | { phase: "saved"; path: string; openError: string | null }
  | { phase: "failed"; stage: "read" | "write"; message: string };

export type ExportableAsset = "summary" | "knowledge-points" | "quiz" | "todo";

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

function quizExportLabels(t: TFunction): QuizExportLabels {
  return {
    assetTitle: t("record.detail.export.quizAsset"),
    questionTypeLabel: t("record.detail.export.questionTypeLabel"),
    stemLabel: t("record.detail.export.stemLabel"),
    difficultyLabel: t("record.detail.export.difficultyLabel"),
    optionsLabel: t("record.detail.export.optionsLabel"),
    userAnswerLabel: t("record.detail.export.userAnswerLabel"),
    resultLabel: t("record.detail.export.resultLabel"),
    correctAnswerLabel: t("record.detail.export.correctAnswerLabel"),
    referenceAnswerLabel: t("record.detail.export.referenceAnswerLabel"),
    explanationLabel: t("record.detail.export.explanationLabel"),
    pendingSelfAssessment: t("record.detail.quiz.shortAnswer.pending"),
    questionTypes: {
      MULTIPLE_CHOICE: t("record.detail.quiz.type.MULTIPLE_CHOICE"),
      MULTIPLE_SELECT: t("record.detail.quiz.type.MULTIPLE_SELECT"),
      TRUE_FALSE: t("record.detail.quiz.type.TRUE_FALSE"),
      FILL_BLANK: t("record.detail.quiz.type.FILL_BLANK"),
      SHORT_ANSWER: t("record.detail.quiz.type.SHORT_ANSWER"),
    },
    difficulties: {
      EASY: t("record.detail.quiz.difficulty.EASY"),
      MEDIUM: t("record.detail.quiz.difficulty.MEDIUM"),
      HARD: t("record.detail.quiz.difficulty.HARD"),
    },
    results: {
      CORRECT: t("record.detail.quiz.result.CORRECT"),
      WRONG: t("record.detail.quiz.result.WRONG"),
    },
  };
}

function isReadableSummaryResponse(
  read: Awaited<ReturnType<typeof recordApi.getSummary>>,
): boolean {
  if (!Object.prototype.hasOwnProperty.call(read, "summary")) return false;
  const summary = read.summary;
  if (summary === null) return true;
  if (
    typeof summary !== "object" ||
    Array.isArray(summary) ||
    typeof summary.status !== "string" ||
    summary.status === ""
  ) {
    return false;
  }
  if (summary.status !== "CONFIRMED") return true;
  return (
    typeof summary.topic === "string" &&
    typeof summary.abstract === "string" &&
    Array.isArray(summary.sections) &&
    summary.sections.every(
      (section) =>
        typeof section === "object" &&
        section !== null &&
        !Array.isArray(section) &&
        typeof section.heading === "string" &&
        Array.isArray(section.points) &&
        section.points.every((point) => typeof point === "string"),
    )
  );
}

/**
 * 学习资产 Markdown 导出：每次触发经 localhost API 重新读取当前资产，
 * 读取完成后立即组装不可变快照文本，再打开系统保存对话框写入用户选择的位置。
 */
export function useRecordExport() {
  const { t } = useTranslation();
  const [state, setState] = useState<RecordExportState>({ phase: "idle" });
  const runningRef = useRef(false);

  const readAsset = useCallback(
    async <T>(read: () => Promise<T>): Promise<T | null> => {
      try {
        return await read();
      } catch (error) {
        setState({
          phase: "failed",
          stage: "read",
          message: `${t("record.detail.export.readFailed")}：${errorMessage(error)}`,
        });
        return null;
      }
    },
    [t],
  );

  const persist = useCallback(
    async (markdown: string, recordTitle: string, assetLabel: string) => {
      const defaultPath = buildExportFileName(
        recordTitle,
        assetLabel,
        t("spaces.records.untitled"),
      );
      try {
        // 用户取消返回 null：不写文件、不报错、不显示成功
        const path = await chooseMarkdownSavePath(defaultPath);
        if (path === null) {
          setState({ phase: "idle" });
          return;
        }
        await writeMarkdownFile(path, markdown);
        setState({ phase: "saved", path, openError: null });
      } catch (error) {
        setState({
          phase: "failed",
          stage: "write",
          message: `${t("record.detail.export.writeFailed")}：${errorMessage(error)}`,
        });
      }
    },
    [t],
  );

  const exportAsset = useCallback(
    async (asset: ExportableAsset, recordId: string, recordTitle: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setState({ phase: "exporting" });
      try {
        if (asset === "summary") {
          const read = await readAsset(() => recordApi.getSummary(recordId));
          if (!read) return;
          const summary = read.summary;
          if (!summary) {
            setState({
              phase: "unavailable",
              message: t("record.detail.export.summaryMissing"),
            });
            return;
          }
          if (summary.status !== "CONFIRMED") {
            setState({
              phase: "unavailable",
              message: t("record.detail.export.summaryNotConfirmed"),
            });
            return;
          }
          const markdown = serializeSummaryMarkdown(
            recordTitle,
            {
              topic: summary.topic,
              abstract: summary.abstract,
              sections: summary.sections.map((section) => ({
                heading: section.heading,
                points: section.points,
              })),
            },
            {
              assetTitle: t("record.detail.export.summaryAsset"),
              topicLabel: t("record.detail.export.summaryTopic"),
              abstractLabel: t("record.detail.export.summaryAbstract"),
            },
          );
          await persist(
            markdown,
            recordTitle,
            t("record.detail.export.summaryAsset"),
          );
          return;
        }

        if (asset === "knowledge-points") {
          const read = await readAsset(() =>
            recordApi.getKnowledgePoints(recordId),
          );
          if (!read) return;
          const items = selectActiveKnowledgePoints(read.items);
          if (!items.length) {
            setState({
              phase: "unavailable",
              message: t("record.detail.export.knowledgePointsEmpty"),
            });
            return;
          }
          const markdown = serializeKnowledgePointsMarkdown(
            recordTitle,
            items,
            {
              assetTitle: t("record.detail.export.knowledgePointsAsset"),
              importanceLabel: t("record.detail.export.importanceLabel"),
              tagsLabel: t("record.detail.export.tagsLabel"),
            },
          );
          await persist(
            markdown,
            recordTitle,
            t("record.detail.export.knowledgePointsAsset"),
          );
          return;
        }

        if (asset === "quiz") {
          const read = await readAsset(() => recordApi.getQuizzes(recordId));
          if (!read) return;
          const items = selectActiveQuizzes(read.items);
          if (!items.length) {
            setState({
              phase: "unavailable",
              message: t("record.detail.export.quizEmpty"),
            });
            return;
          }
          const markdown = serializeQuizMarkdown(
            recordTitle,
            items,
            quizExportLabels(t),
          );
          await persist(
            markdown,
            recordTitle,
            t("record.detail.export.quizAsset"),
          );
          return;
        }

        const read = await readAsset(() => recordApi.getTodos(recordId));
        if (!read) return;
        const items = selectFormalTodos(read.items);
        if (!items.length) {
          setState({
            phase: "unavailable",
            message: t("record.detail.export.todoEmpty"),
          });
          return;
        }
        const assetTitle = t("record.detail.export.todoAsset");
        await persist(
          serializeTodoMarkdown(recordTitle, items, assetTitle),
          recordTitle,
          assetTitle,
        );
      } finally {
        runningRef.current = false;
      }
    },
    [persist, readAsset, t],
  );

  const exportAll = useCallback(
    async (recordId: string, recordTitle: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setState({ phase: "exporting" });
      try {
        const [summaryRead, knowledgePointRead, quizRead, todoRead] =
          await Promise.all([
            recordApi.getSummary(recordId),
            recordApi.getKnowledgePoints(recordId),
            recordApi.getQuizzes(recordId),
            recordApi.getTodos(recordId),
          ]);
        if (!isReadableSummaryResponse(summaryRead)) {
          throw new Error(t("record.detail.export.invalidResponse"));
        }
        const summary = summaryRead.summary;
        const knowledgePoints = selectActiveKnowledgePoints(
          knowledgePointRead.items,
        );
        const quizzes = selectActiveQuizzes(quizRead.items);
        const todos = selectFormalTodos(todoRead.items);
        const markdown = serializeAggregateMarkdown(recordTitle, [
          summary?.status === "CONFIRMED"
            ? serializeSummaryMarkdown(
                recordTitle,
                {
                  topic: summary.topic,
                  abstract: summary.abstract,
                  sections: summary.sections.map((section) => ({
                    heading: section.heading,
                    points: section.points,
                  })),
                },
                {
                  assetTitle: t("record.detail.export.summaryAsset"),
                  topicLabel: t("record.detail.export.summaryTopic"),
                  abstractLabel: t("record.detail.export.summaryAbstract"),
                },
              )
            : null,
          knowledgePoints.length
            ? serializeKnowledgePointsMarkdown(recordTitle, knowledgePoints, {
                assetTitle: t("record.detail.export.knowledgePointsAsset"),
                importanceLabel: t("record.detail.export.importanceLabel"),
                tagsLabel: t("record.detail.export.tagsLabel"),
              })
            : null,
          quizzes.length
            ? serializeQuizMarkdown(recordTitle, quizzes, quizExportLabels(t))
            : null,
          todos.length
            ? serializeTodoMarkdown(
                recordTitle,
                todos,
                t("record.detail.export.todoAsset"),
              )
            : null,
        ]);
        if (markdown === null) {
          setState({
            phase: "unavailable",
            message: t("record.detail.export.allEmpty"),
          });
          return;
        }
        await persist(
          markdown,
          recordTitle,
          t("record.detail.export.allAssetsFileLabel"),
        );
      } catch (error) {
        setState({
          phase: "failed",
          stage: "read",
          message: `${t("record.detail.export.readFailed")}：${errorMessage(error)}`,
        });
      } finally {
        runningRef.current = false;
      }
    },
    [persist, t],
  );

  const openSavedFile = useCallback(async (path: string) => {
    try {
      await openExportedFile(path);
    } catch (error) {
      setState((previous) =>
        previous.phase === "saved"
          ? { ...previous, openError: errorMessage(error) }
          : previous,
      );
    }
  }, []);

  return { state, exportAsset, exportAll, openSavedFile };
}
