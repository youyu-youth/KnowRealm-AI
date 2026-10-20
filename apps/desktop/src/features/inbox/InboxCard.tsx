import { ContextMenu } from "@base-ui/react/context-menu";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  AudioLines,
  ClipboardPaste,
  Eye,
  FileText,
  FolderInput,
  MoreHorizontal,
  PencilLine,
  Rocket,
  Trash2,
} from "lucide-react";
import { useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { AppTooltip } from "@/components/common/AppTooltip";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Spinner } from "@/components/ui/spinner";
import { InboxRowActions } from "@/features/inbox/InboxRowActions";
import {
  formatInboxListDate,
  inboxMetaText,
  inboxStatusClassNames,
  ORGANIZABLE_STATUSES,
  PROCESSING_STATUSES,
} from "@/features/inbox/inboxPresentation";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { InboxRecordOut } from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  statusLabelKeys,
} from "@/features/records/recordPresentation";

export function InboxCard({
  record,
  selected,
  checked,
  disabled,
  onCheckedChange,
  onPreview,
  onClassified,
  onDragStart,
  onDragEnd,
}: {
  record: InboxRecordOut;
  selected: boolean;
  checked: boolean;
  disabled: boolean;
  onCheckedChange: (checked: boolean) => void;
  onPreview: () => void;
  onClassified: (courseName: string) => void;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
}) {
  const { t } = useTranslation();
  const [action, setAction] = useState<
    "classify" | "upgrade" | "delete" | null
  >(null);
  const title = record.title.trim() || t("spaces.records.untitled");
  const organizable = ORGANIZABLE_STATUSES.has(record.status);
  const processing = PROCESSING_STATUSES.has(record.status);
  const audio =
    record.capture_type === "RECORDING" ||
    record.capture_type === "AUDIO_IMPORT";
  const document = record.capture_type === "DOCUMENT_IMPORT";
  const Icon = audio
    ? AudioLines
    : record.capture_type === "QUICK_NOTE"
      ? PencilLine
      : record.capture_type === "PASTE"
        ? ClipboardPaste
        : FileText;
  const transcript = useQuery({
    queryKey: recordKeys.transcript(record.id),
    queryFn: () => recordApi.getTranscript(record.id),
    enabled: !processing && record.status !== "FAILED",
  });
  const jobs = useQuery({
    queryKey: recordKeys.jobs(record.id),
    queryFn: () => recordApi.getJobs(record.id),
    enabled: processing,
    refetchInterval: processing ? 2_000 : false,
  });
  const progress = jobs.data
    ? Math.round(Math.min(1, Math.max(0, jobs.data.progress)) * 100)
    : null;
  const waitingReason = jobs.data?.jobs.find(
    (job) => job.status === "PENDING" || job.status === "RUNNING",
  )?.waiting_reason;
  const rawContent = transcript.data?.transcript?.content;
  const content =
    rawContent?.split("\n")[0].trim() === record.title.trim() &&
    rawContent.includes("\n")
      ? rawContent.slice(rawContent.indexOf("\n") + 1).trim()
      : rawContent;
  const items = (
    <>
      <DropdownMenuItem onClick={onPreview}>
        <Eye aria-hidden="true" />
        {t("inbox.workspace.preview")}
      </DropdownMenuItem>
      <DropdownMenuItem
        render={
          <Link
            to="/records/$recordId"
            params={{ recordId: record.id }}
            search={{ tab: "transcript" }}
          />
        }
      >
        <FileText aria-hidden="true" />
        {t("inbox.openRecordShort")}
      </DropdownMenuItem>
      <DropdownMenuItem
        disabled={!organizable || disabled}
        onClick={() => setAction("classify")}
      >
        <FolderInput aria-hidden="true" />
        {t("inbox.classify.title")}
      </DropdownMenuItem>
      <DropdownMenuItem
        disabled={!organizable || disabled}
        onClick={() => setAction("upgrade")}
      >
        <Rocket aria-hidden="true" />
        {t("inbox.upgrade.short")}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        variant="destructive"
        disabled={disabled}
        onClick={() => setAction("delete")}
      >
        <Trash2 aria-hidden="true" />
        {t("inbox.delete.confirm")}
      </DropdownMenuItem>
    </>
  );
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger
        render={<li />}
        className="inbox-card group"
        data-selected={checked || selected || undefined}
        draggable={organizable && !disabled}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-muted-foreground flex size-6 shrink-0 items-center justify-center">
            <Icon aria-hidden="true" className="size-4" />
          </span>
          <span className="text-label text-muted-foreground min-w-0 flex-1 truncate">
            {t(captureTypeLabelKeys[record.capture_type])}
          </span>
          <Checkbox
            checked={checked}
            disabled={disabled}
            onCheckedChange={onCheckedChange}
            aria-label={t("inbox.selection.record", { title })}
          />
          <DropdownMenu>
            <AppTooltip label={t("inbox.workspace.more", { title })} side="top">
              <DropdownMenuTrigger
                render={<Button variant="ghost" size="icon-sm" />}
                aria-label={t("inbox.workspace.more", { title })}
              >
                <MoreHorizontal aria-hidden="true" />
              </DropdownMenuTrigger>
            </AppTooltip>
            <DropdownMenuContent align="end" className="inbox-menu w-56">
              {items}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <Link
          to="/records/$recordId"
          params={{ recordId: record.id }}
          search={{ tab: "transcript" }}
          className="text-inbox-card text-ink focus-visible:ring-ring mt-3 line-clamp-2 rounded-sm font-semibold break-words hover:underline focus-visible:ring-2"
          title={title}
        >
          {title}
        </Link>
        <button
          type="button"
          onClick={onPreview}
          className="inbox-card-preview focus-visible:ring-ring mt-2 flex min-h-16 min-w-0 flex-1 items-start gap-3 rounded-md text-left focus-visible:ring-2"
          aria-label={t("inbox.preview.action", { title })}
        >
          {audio ? (
            <span className="bg-surface-subtle text-muted-foreground flex w-full items-center gap-3 rounded-lg px-3 py-4">
              <AudioLines aria-hidden="true" className="size-7 shrink-0" />
              <span className="text-body-dense">
                {t("inbox.workspace.audioPreview")}
              </span>
            </span>
          ) : (
            <>
              {document ? (
                <span className="inbox-document-thumb" aria-hidden="true">
                  <FileText className="size-8" />
                  <span />
                  <span />
                  <span />
                </span>
              ) : null}
              <span className="text-body text-muted-foreground line-clamp-3 break-words">
                {content ||
                  (transcript.isError
                    ? t("inbox.preview.error")
                    : transcript.isFetching
                      ? t("inbox.preview.loading")
                      : t(`inbox.preview.availability.${record.status}`))}
              </span>
            </>
          )}
        </button>
        {processing ? (
          <div
            className="bg-surface-strong mt-3 h-1.5 overflow-hidden rounded-full"
            role="progressbar"
            aria-label={t(statusLabelKeys[record.status])}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress ?? undefined}
          >
            <div
              className="bg-chat-accent h-full"
              style={{ width: `${progress ?? 0}%` }}
            />
          </div>
        ) : null}
        <div className="text-label text-muted-foreground mt-4 flex flex-wrap items-center justify-between gap-2">
          <span
            className={`${inboxStatusClassNames[record.status]} inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-medium`}
          >
            {processing && !waitingReason ? (
              <Spinner className="size-3" aria-hidden="true" />
            ) : null}
            {t(
              waitingReason
                ? `inbox.workspace.waiting.${waitingReason}`
                : statusLabelKeys[record.status],
            )}
            {processing && !waitingReason && progress !== null
              ? ` ${progress}%`
              : ""}
          </span>
          <span className="min-w-0 flex-1 text-right">
            {inboxMetaText(record, t)}
          </span>
        </div>
        <div className="mt-2 flex min-h-8 items-center justify-between gap-2">
          <time
            dateTime={record.created_at}
            title={new Date(record.created_at).toLocaleString()}
            className="text-label text-muted-foreground min-w-0 tabular-nums"
          >
            {formatInboxListDate(record.created_at)}
          </time>
          <div
            className="inbox-card-actions"
            aria-label={t("inbox.workspace.actions", { title })}
          >
            <AppTooltip
              label={t("inbox.workspace.quickPreview", { title })}
              side="top"
            >
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("inbox.workspace.quickPreview", { title })}
                onClick={onPreview}
              >
                <Eye aria-hidden="true" />
              </Button>
            </AppTooltip>
            <InboxRowActions
              record={record}
              onClassified={onClassified}
              compact
              disabled={disabled}
              action={action}
              onActionChange={setAction}
            />
          </div>
        </div>
      </ContextMenu.Trigger>
      <DropdownMenuContent className="inbox-menu w-56">
        {items}
      </DropdownMenuContent>
    </ContextMenu.Root>
  );
}
