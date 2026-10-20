import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowUpRight,
  AudioLines,
  FileText,
  Globe,
  StickyNote,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import type { CaptureType, RecordStatus } from "@/features/records/api/types";
import { statusLabelKeys } from "@/features/records/recordPresentation";
import { TodayItemMenu } from "@/features/today/components/TodayItemMenu";

export function TodayPendingRecord({
  item,
}: {
  item: {
    id: string;
    title: string;
    detail: string;
    status: RecordStatus;
    captureType?: CaptureType;
  };
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const awaiting = item.status === "SUMMARY_READY";
  const Icon =
    item.captureType === "AUDIO_IMPORT" || item.captureType === "RECORDING"
      ? AudioLines
      : item.captureType === "CLIP"
        ? Globe
        : item.captureType === "QUICK_NOTE"
          ? StickyNote
          : FileText;
  return (
    <TodayItemMenu
      title={item.title}
      quickAction={false}
      className="today-pending-record"
      actions={[
        {
          label: t("today.workspace.openRecord", { title: item.title }),
          icon: ArrowUpRight,
          run: () =>
            void navigate({
              to: "/records/$recordId",
              params: { recordId: item.id },
            }),
        },
        {
          label: t("today.workspace.preview.viewSource"),
          icon: FileText,
          run: () =>
            void navigate({
              to: "/records/$recordId",
              params: { recordId: item.id },
              search: { tab: "transcript" },
            }),
        },
      ]}
    >
      <Link
        to="/records/$recordId"
        params={{ recordId: item.id }}
        aria-label={t("today.workspace.openRecord", { title: item.title })}
        className="today-pending-record-link"
      >
        <span className="today-pending-record-icon">
          <Icon aria-hidden="true" />
        </span>
        <span className="today-pending-record-copy">
          <span className="today-pending-record-title" title={item.title}>
            {item.title}
          </span>
          <span className="today-pending-record-meta">
            <span className="truncate" title={item.detail}>
              {item.detail}
            </span>
            <StatusTag
              tone={
                item.status === "FAILED"
                  ? "danger"
                  : awaiting
                    ? "warning"
                    : "neutral"
              }
            >
              {t(
                awaiting
                  ? "today.workspace.awaiting"
                  : statusLabelKeys[item.status],
              )}
            </StatusTag>
          </span>
        </span>
      </Link>
    </TodayItemMenu>
  );
}
