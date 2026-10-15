import { ContextMenu } from "@base-ui/react/context-menu";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  FileText,
  FileCode2,
  FileType2,
  Headphones,
  PanelRightOpen,
  Sparkles,
  Globe,
  GraduationCap,
  Lightbulb,
  Mic,
  MoreHorizontal,
  Star,
  StickyNote,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { libraryCardFormat } from "../libraryCardFormat";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";
import {
  libraryApi,
  useToggleFavorite,
  type LibraryItemOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { cn, formatSize } from "@/lib/utils";

export type LibraryCardEntry = {
  id: string;
  sourceType: LibraryItemOut["source_type"] | "ASSET";
  title: string;
  updatedAt: string;
  courseName?: string | null;
  detail?: string;
  durationMs?: number;
  status?: string;
  item?: LibraryItemOut;
};

const icons = {
  audio: Headphones,
  markdown: FileCode2,
  pdf: FileType2,
  docx: FileText,
  html: Globe,
  txt: StickyNote,
  document: FileText,
  book: BookOpen,
  asset: Lightbulb,
};

function ContentPreview({ item }: { item: LibraryItemOut }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!ref.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  const preview = useQuery({
    queryKey: [...libraryKeys.itemContent(item.id), "preview"],
    queryFn: () => libraryApi.getItemContent(item.id, 800),
    enabled:
      visible && item.availability === "RETRIEVABLE" && item.deleted_at == null,
    staleTime: 60_000,
  });
  return (
    <span ref={ref} className="library-card-excerpt">
      <span className="library-card-excerpt-text">
        {preview.data?.content ||
          (preview.isError
            ? t("library.cards.previewError")
            : t("library.cards.openPreview"))}
      </span>
    </span>
  );
}

export function LibraryCard({
  entry,
  selected,
  onSelect,
}: {
  entry: LibraryCardEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t, i18n } = useTranslation();
  const favorite = useToggleFavorite();
  const createChat = useCreateChatSession();
  const item = entry.item;
  const format = libraryCardFormat(entry.sourceType, item);
  const Icon = icons[format];
  const formatLabel = t(`library.cards.formats.${format}`);
  const web = entry.sourceType === "WEB";
  const audio = entry.sourceType === "AUDIO";
  let host: string | undefined;
  if (web && item?.origin_uri) {
    try {
      host = new URL(item.origin_uri).hostname;
    } catch {
      /* 历史来源可能不是有效 URL。 */
    }
  }
  const date = new Date(entry.updatedAt);
  const toggleFavorite = () => {
    if (item) favorite.mutate({ itemId: item.id, favorite: !item.favorite });
  };
  const interpret = () => {
    if (item)
      createChat.mutate({
        mode: "ASK",
        scope: "LIBRARY_ITEM",
        library_item_id: item.id,
      });
  };
  const menuItems = (
    <>
      <DropdownMenuItem onClick={onSelect}>
        <PanelRightOpen aria-hidden />
        {t("library.cards.openDetails")}
      </DropdownMenuItem>
      {item && item.deleted_at == null ? (
        <>
          <DropdownMenuItem
            onClick={toggleFavorite}
            disabled={favorite.isPending}
          >
            <Star
              aria-hidden
              className={item.favorite ? "fill-current" : undefined}
            />
            {t(
              item.favorite
                ? "library.cards.unfavorite"
                : "library.favoriteToggle",
            )}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={interpret}
            disabled={createChat.isPending || item.status === "ARCHIVED"}
          >
            <Sparkles aria-hidden />
            {t("library.inspector.aiInterpret")}
          </DropdownMenuItem>
        </>
      ) : null}
    </>
  );
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger
        render={<article />}
        className={cn("library-card", selected && "library-card-selected")}
        data-kind={entry.sourceType}
        data-format={format}
        data-failed={item?.availability === "FAILED" || undefined}
      >
        <div className="library-card-toolbar">
          <span className="library-card-format">
            <span className="library-card-format-icon">
              <Icon className="size-4" aria-hidden />
            </span>
            <span className="truncate">{formatLabel}</span>
          </span>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {web && item && item.deleted_at == null ? (
              <Button
                className="library-card-interpret"
                variant="default"
                size="sm"
                disabled={createChat.isPending || item.status === "ARCHIVED"}
                onClick={interpret}
              >
                {t("library.inspector.aiInterpret")}
              </Button>
            ) : null}
            {item && item.deleted_at == null ? (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("library.favoriteToggle")}
                aria-pressed={item.favorite}
                disabled={favorite.isPending}
                onClick={toggleFavorite}
              >
                <Star
                  className={item.favorite ? "fill-current" : undefined}
                  aria-hidden
                />
              </Button>
            ) : null}
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="ghost" size="icon-sm" />}
                aria-label={t("library.cards.actions", { title: entry.title })}
              >
                <MoreHorizontal aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                {menuItems}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <button
          type="button"
          className="library-card-body"
          onClick={onSelect}
          aria-pressed={selected}
          aria-label={entry.title}
        >
          {host ? <span className="library-card-host">{host}</span> : null}
          <span
            className={cn(
              "library-card-title",
              web && "library-card-web-title",
            )}
          >
            {entry.title}
          </span>
          {audio ? (
            <span className="library-audio-preview">
              <Mic className="size-5 shrink-0" aria-hidden />
              <span className="library-waveform" aria-hidden>
                {Array.from({ length: 36 }, (_, index) => (
                  <i key={index} />
                ))}
              </span>
              <span className="shrink-0 text-xs tabular-nums">
                {entry.durationMs
                  ? `${Math.floor(entry.durationMs / 60000)}:${String(Math.floor(entry.durationMs / 1000) % 60).padStart(2, "0")}`
                  : t("library.sourceTypes.AUDIO")}
              </span>
            </span>
          ) : item?.availability === "FAILED" ? (
            <span className="text-destructive text-body">
              {t("library.inspector.failedHint")}
            </span>
          ) : entry.detail ? (
            <span className="library-card-excerpt">
              <span className="library-card-excerpt-text">{entry.detail}</span>
            </span>
          ) : item ? (
            <ContentPreview item={item} />
          ) : (
            <span className="library-card-excerpt">
              <span className="library-card-excerpt-text">
                {t("library.cards.recordPreview")}
              </span>
            </span>
          )}
          {audio ? (
            <span className="text-ink-muted text-label">
              {t("library.cards.waveformDemo")}
            </span>
          ) : null}
          <span className="library-card-footer">
            <span className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <span className="flex min-w-0 items-center gap-1.5">
                <Icon className="size-3.5 shrink-0" aria-hidden />
                {formatLabel}
                {item?.file_size != null
                  ? ` · ${formatSize(item.file_size)}`
                  : ""}
              </span>
              <time dateTime={entry.updatedAt} className="tabular-nums">
                {Number.isNaN(date.getTime())
                  ? entry.updatedAt
                  : date.toLocaleDateString(i18n.language)}
              </time>
            </span>
            {item ? (
              <span
                className="library-card-status"
                data-status={item.availability}
              >
                <span aria-hidden />
                {t(`library.availability.${item.availability}`)}
              </span>
            ) : entry.status ? (
              <span>{entry.status}</span>
            ) : null}
            <span className="flex items-center gap-2">
              <GraduationCap className="size-4 shrink-0" aria-hidden />
              <span className="truncate">
                {entry.courseName ?? t("library.filters.unclassified")}
              </span>
            </span>
          </span>
        </button>
        {favorite.isError ? (
          <p role="alert" className="text-destructive text-label px-4 pb-3">
            {favorite.error.message}
          </p>
        ) : null}
        {createChat.isError ? (
          <p role="alert" className="text-destructive text-label px-4 pb-3">
            {createChat.error.message}
          </p>
        ) : null}
      </ContextMenu.Trigger>
      <DropdownMenuContent className="w-52">{menuItems}</DropdownMenuContent>
    </ContextMenu.Root>
  );
}
