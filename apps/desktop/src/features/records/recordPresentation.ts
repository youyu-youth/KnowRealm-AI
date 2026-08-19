import type { TFunction } from "i18next";
import type { CaptureType, RecordStatus } from "@/features/records/api/types";

export const captureTypeLabelKeys = {
  RECORDING: "spaces.records.captureType.RECORDING",
  AUDIO_IMPORT: "spaces.records.captureType.AUDIO_IMPORT",
  DOCUMENT_IMPORT: "spaces.records.captureType.DOCUMENT_IMPORT",
  PASTE: "spaces.records.captureType.PASTE",
  QUICK_NOTE: "spaces.records.captureType.QUICK_NOTE",
  CLIP: "spaces.records.captureType.CLIP",
} satisfies Record<CaptureType, string>;

export const statusLabelKeys = {
  NOTE: "spaces.records.status.NOTE",
  DRAFT: "spaces.records.status.DRAFT",
  CONTENT_PROCESSING: "spaces.records.status.CONTENT_PROCESSING",
  SUMMARY_PENDING: "spaces.records.status.SUMMARY_PENDING",
  SUMMARY_PROCESSING: "spaces.records.status.SUMMARY_PROCESSING",
  SUMMARY_READY: "spaces.records.status.SUMMARY_READY",
  COMPLETED: "spaces.records.status.COMPLETED",
  FAILED: "spaces.records.status.FAILED",
} satisfies Record<RecordStatus, string>;

export const statusClassNames = {
  NOTE: "bg-surface-subtle text-muted-foreground",
  DRAFT: "bg-surface-subtle text-muted-foreground",
  CONTENT_PROCESSING: "bg-learning-soft text-learning",
  SUMMARY_PENDING: "bg-learning-soft text-learning",
  SUMMARY_PROCESSING: "bg-learning-soft text-learning",
  SUMMARY_READY: "bg-learning-soft text-learning",
  COMPLETED: "bg-surface-subtle text-ink",
  FAILED: "bg-destructive/10 text-destructive",
} satisfies Record<RecordStatus, string>;

export const recordDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatRecordDuration(durationMs: number, t: TFunction): string {
  const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [
    hours ? t("spaces.records.duration.hours", { count: hours }) : null,
    minutes ? t("spaces.records.duration.minutes", { count: minutes }) : null,
    seconds ? t("spaces.records.duration.seconds", { count: seconds }) : null,
  ]
    .filter(Boolean)
    .join(" ");
}
