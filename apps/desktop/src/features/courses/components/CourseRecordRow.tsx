import { Link } from "@tanstack/react-router";
import {
  ClipboardPaste,
  FileAudio,
  FileText,
  Layers3,
  Mic,
  Scissors,
  StickyNote,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CaptureType, RecordOut } from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";
import { cn } from "@/lib/utils";

const captureTypeIcons = {
  RECORDING: Mic,
  AUDIO_IMPORT: FileAudio,
  DOCUMENT_IMPORT: FileText,
  MULTI_SOURCE: Layers3,
  PASTE: ClipboardPaste,
  QUICK_NOTE: StickyNote,
  CLIP: Scissors,
} satisfies Record<CaptureType, typeof Mic>;

type CourseRecordRowProps = {
  record: RecordOut;
  /** full = 学习记录标签页（类型 + 创建时间 + 时长 + 状态）；compact = 概览最近记录。 */
  variant?: "full" | "compact";
};

/** 学习记录行：标签页与「最近学习记录」卡共用同一数据呈现。 */
export function CourseRecordRow({
  record,
  variant = "full",
}: CourseRecordRowProps) {
  const { t, i18n } = useTranslation();
  const title = record.title.trim() || t("spaces.records.untitled");
  const Icon = captureTypeIcons[record.capture_type] ?? FileText;

  return (
    <Link
      to="/records/$recordId"
      params={{ recordId: record.id }}
      className="hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 flex min-w-0 items-center gap-3 rounded-lg px-2 py-2.5 transition-colors duration-[120ms] focus-visible:ring-3"
    >
      <span className="border-border-subtle bg-surface-subtle text-ink-muted flex size-8 shrink-0 items-center justify-center rounded-lg border">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span
          className="text-body-dense text-ink-strong block truncate font-medium"
          title={title}
        >
          {title}
        </span>
        <span className="text-label text-ink-muted mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          {variant === "full" ? (
            <>
              <span>{t(captureTypeLabelKeys[record.capture_type])}</span>
              <span aria-hidden="true">·</span>
              <time dateTime={record.created_at}>
                {t("spaces.records.createdAt", {
                  date: recordDateFormatter.format(new Date(record.created_at)),
                })}
              </time>
            </>
          ) : (
            <time dateTime={record.created_at}>
              {formatCourseMoment(
                record.created_at,
                t("spaces.time.yesterdayAt"),
                i18n.resolvedLanguage ?? "zh-CN",
              )}
            </time>
          )}
          {record.duration_ms > 0 ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{formatRecordDuration(record.duration_ms, t)}</span>
            </>
          ) : null}
        </span>
      </span>
      {variant === "compact" ? (
        <span className="course-record-open" aria-hidden="true">
          {t("spaces.courseDetail.recentRecords.open")}
        </span>
      ) : null}
      {variant === "full" ? (
        <span
          className={cn(
            "text-label font-label rounded-xs px-2 py-1 whitespace-nowrap",
            statusClassNames[record.status],
          )}
        >
          {t(statusLabelKeys[record.status])}
        </span>
      ) : null}
    </Link>
  );
}
