import { useMemo, useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import {
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Star,
  Trash2,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChatSession } from "@/features/chat/api/types";
import {
  DeleteChatDialog,
  RenameChatDialog,
} from "@/features/chat/ChatSessionDialogs";
import { NewChatButton } from "@/features/chat/NewChatButton";
import { formatChatTimestamp } from "@/features/chat/chatTime";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { useCourseNames } from "@/features/chat/useCourseNames";
import { cn } from "@/lib/utils";

type SessionFilter = "all" | "today" | "week" | "favorite";

const FILTER_IDS: SessionFilter[] = ["all", "today", "week", "favorite"];

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

type ChatSessionSidebarProps = {
  sessions: UseQueryResult<ChatSession[]>;
  activeSessionId?: string;
};

/** 左栏「对话记录」：筛选 + 会话列表（行内 … 菜单：收藏/重命名/删除）。 */
export function ChatSessionSidebar({
  sessions,
  activeSessionId,
}: ChatSessionSidebarProps) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<SessionFilter>("all");
  const favoriteSessionIds = useChatUiStore(
    (state) => state.favoriteSessionIds,
  );

  const visibleSessions = useMemo(() => {
    const list = sessions.data ?? [];
    if (filter === "all") return list;
    if (filter === "favorite") {
      return list.filter((session) => favoriteSessionIds.has(session.id));
    }
    const now = new Date();
    const cutoff =
      filter === "today"
        ? new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
        : now.getTime() - WEEK_MS;
    return list.filter(
      (session) => new Date(session.updated_at).getTime() >= cutoff,
    );
  }, [sessions.data, filter, favoriteSessionIds]);

  return (
    <aside
      className="border-border-subtle flex w-70 shrink-0 flex-col border-r"
      aria-label={t("chat.listLabel")}
    >
      <div className="flex items-center justify-between gap-2 px-4 pt-5 pb-3">
        <h2 className="text-section font-section text-ink-strong">
          {t("chat.recordsTitle")}
        </h2>
        <NewChatButton labelKey="chat.newSession" variant="outline" />
      </div>

      <div className="flex flex-wrap gap-1 px-4 pb-3">
        {FILTER_IDS.map((id) => (
          <button
            key={id}
            type="button"
            aria-pressed={filter === id}
            className={cn(
              "text-label focus-visible:ring-ring/40 rounded-full border px-2 py-0.5 transition-colors focus-visible:ring-3",
              filter === id
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border-subtle bg-surface-raised text-ink-muted hover:text-ink",
            )}
            onClick={() => setFilter(id)}
          >
            {t(`chat.filter.${id}`)}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {sessions.isPending ? (
          <p
            role="status"
            className="text-label text-muted-foreground flex items-center gap-2 px-2 py-3"
          >
            <Spinner aria-hidden="true" className="size-3" />
            {t("chat.loading")}
          </p>
        ) : sessions.isError ? (
          <Alert variant="destructive" className="mx-1">
            <AlertDescription>{sessions.error.message}</AlertDescription>
          </Alert>
        ) : visibleSessions.length === 0 ? (
          <p className="text-label text-muted-foreground px-2 py-3">
            {filter === "all" ? t("chat.emptyTitle") : t("chat.filter.empty")}
          </p>
        ) : (
          <ul
            aria-label={t("chat.listLabel")}
            className="flex flex-col gap-0.5"
          >
            {visibleSessions.map((session) => (
              <ChatSessionRow
                key={session.id}
                session={session}
                active={session.id === activeSessionId}
              />
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

function ChatSessionRow({
  session,
  active,
}: {
  session: ChatSession;
  active: boolean;
}) {
  const { t, i18n } = useTranslation();
  const favoriteSessionIds = useChatUiStore(
    (state) => state.favoriteSessionIds,
  );
  const toggleFavorite = useChatUiStore((state) => state.toggleFavorite);
  const courseNames = useCourseNames();
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const title = session.title ?? t("chat.untitled");
  const favorited = favoriteSessionIds.has(session.id);
  const scopeLabel =
    session.scope === "COURSE"
      ? (courseNames.get(session.course_id ?? "") ?? t("chat.scope.course"))
      : session.scope === "ALL"
        ? t("chat.scope.all")
        : null;

  return (
    <li>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-lg pr-1.5 transition-colors",
          active ? "bg-surface-subtle" : "hover:bg-surface-subtle/60",
        )}
      >
        <Link
          to="/chat/$sessionId"
          params={{ sessionId: session.id }}
          className="focus-visible:ring-ring/40 flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-2.5 py-2.5 focus-visible:ring-3"
        >
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full",
              active ? "bg-surface-strong" : "bg-surface-subtle",
            )}
          >
            <MessageSquare
              className="text-ink-muted size-4"
              aria-hidden="true"
            />
          </span>
          <span className="min-w-0 flex-1">
            <span
              className="text-body text-ink block truncate font-medium"
              title={title}
            >
              {title}
            </span>
            <span className="text-label text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <span
                className="shrink-0"
                title={t(`chat.agents.${session.agent_id}.name`)}
              >
                {t(`chat.agents.${session.agent_id}.name`)}
              </span>
              {session.record_deleted ? (
                <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                  {t("chat.recordDeleted")}
                </span>
              ) : null}
              {session.course_deleted ? (
                <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                  {t("chat.courseDeleted")}
                </span>
              ) : null}
              {session.mode === "RESEARCH" ? (
                <span className="bg-chat-accent-soft text-chat-accent rounded-xs px-1.5 py-px">
                  {t("chat.badge.research")}
                </span>
              ) : null}
              {scopeLabel ? (
                <span className="bg-surface-strong text-ink-muted rounded-xs px-1.5 py-px">
                  {scopeLabel}
                </span>
              ) : null}
              <time dateTime={session.updated_at}>
                {formatChatTimestamp(t, i18n.language, session.updated_at)}
              </time>
            </span>
          </span>
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("chat.menu.action", { title })}
                className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 data-popup-open:opacity-100"
              />
            }
          >
            <MoreHorizontal aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={() => toggleFavorite(session.id)}>
              <Star
                aria-hidden="true"
                className={favorited ? "fill-current" : undefined}
              />
              {favorited ? t("chat.menu.unfavorite") : t("chat.menu.favorite")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setRenameOpen(true)}>
              <Pencil aria-hidden="true" />
              {t("chat.menu.rename")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 aria-hidden="true" />
              {t("chat.menu.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <RenameChatDialog
        sessionId={session.id}
        displayTitle={title}
        hasCustomTitle={session.title !== null}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
      <DeleteChatDialog
        sessionId={session.id}
        title={title}
        wasActive={active}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </li>
  );
}
