import type { TFunction } from "i18next";
import { formatSize } from "@/lib/utils";
import type { InboxRecordOut, RecordOut } from "@/features/records/api/types";
import {
  formatRecordDuration,
  recordDateFormatter,
} from "@/features/records/recordPresentation";

export const ORGANIZABLE_STATUSES = new Set(["NOTE", "SUMMARY_PENDING"]);
export const PROCESSING_STATUSES = new Set([
  "DRAFT",
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export const inboxStatusClassNames = {
  NOTE: "bg-success-soft text-success-foreground",
  DRAFT: "bg-surface-subtle text-muted-foreground",
  CONTENT_PROCESSING: "bg-chat-accent-soft text-chat-accent",
  SUMMARY_PENDING: "bg-chat-accent-soft text-chat-accent",
  SUMMARY_PROCESSING: "bg-chat-accent-soft text-chat-accent",
  SUMMARY_READY: "bg-success-soft text-success-foreground",
  COMPLETED: "bg-surface-subtle text-ink",
  FAILED: "bg-danger-soft text-destructive",
} satisfies Record<RecordOut["status"], string>;

const listTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function inboxMetaText(record: InboxRecordOut, t: TFunction): string {
  const parts: string[] = [];
  const isAudio = ["RECORDING", "AUDIO_IMPORT"].includes(record.capture_type);
  const isText = ["QUICK_NOTE", "PASTE"].includes(record.capture_type);
  if (isAudio && record.duration_ms > 0) {
    parts.push(
      t("inbox.meta.duration", {
        duration: formatRecordDuration(record.duration_ms, t),
      }),
    );
  }
  if (!isText) {
    const size = formatSize(record.file_size_bytes ?? null);
    if (size) parts.push(size);
  }
  if (
    !isAudio &&
    (isText ||
      record.capture_type === "MULTI_SOURCE" ||
      record.capture_type === "CLIP") &&
    record.content_chars != null
  ) {
    parts.push(t("inbox.meta.characters", { count: record.content_chars }));
  }
  return parts.join(" · ");
}

export function isToday(value: string) {
  const date = new Date(value);
  const today = new Date();
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

export function formatInboxListDate(value: string) {
  return isToday(value)
    ? listTimeFormatter.format(new Date(value))
    : recordDateFormatter.format(new Date(value));
}
