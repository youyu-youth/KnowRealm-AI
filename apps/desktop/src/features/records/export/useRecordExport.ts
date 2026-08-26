import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { recordApi } from "@/features/records/api/records";
import {
  buildExportFileName,
  selectActiveKnowledgePoints,
  serializeKnowledgePointsMarkdown,
  serializeSummaryMarkdown,
} from "@/features/records/export/serializers";
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

export type ExportableAsset = "summary" | "knowledge-points";

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
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
        const markdown = serializeKnowledgePointsMarkdown(recordTitle, items, {
          assetTitle: t("record.detail.export.knowledgePointsAsset"),
          importanceLabel: t("record.detail.export.importanceLabel"),
          tagsLabel: t("record.detail.export.tagsLabel"),
        });
        await persist(
          markdown,
          recordTitle,
          t("record.detail.export.knowledgePointsAsset"),
        );
      } finally {
        runningRef.current = false;
      }
    },
    [persist, readAsset, t],
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

  return { state, exportAsset, openSavedFile };
}
