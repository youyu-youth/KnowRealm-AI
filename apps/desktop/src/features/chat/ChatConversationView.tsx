import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  GraduationCap,
  Library,
  MoreHorizontal,
  Pencil,
  Star,
  Telescope,
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
import type { ChatMessage, ChatSession } from "@/features/chat/api/types";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { ChatExecutedOperationCard } from "@/features/chat/ChatExecutedOperationCard";
import { ChatMemoryProposalCard } from "@/features/chat/ChatMemoryProposalCard";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import { ChatOperationProposalCard } from "@/features/chat/ChatOperationProposalCard";
import { ChatResearchProposalCard } from "@/features/chat/ChatResearchProposalCard";
import {
  ChatScopeChips,
  type ScopeChipId,
} from "@/features/chat/ChatScopeChips";
import {
  DeleteChatDialog,
  RenameChatDialog,
} from "@/features/chat/ChatSessionDialogs";
import { ChatSuggestions } from "@/features/chat/ChatSuggestions";
import { CoursePickerDialog } from "@/features/chat/CoursePickerDialog";
import { RecordMountDialog } from "@/features/chat/RecordMountDialog";
import { formatChatTimestamp } from "@/features/chat/chatTime";
import {
  selectWebSearchEnabled,
  useChatUiStore,
} from "@/features/chat/chatUiStore";
import { useChatStream } from "@/features/chat/useChatStream";
import { useCourseNames } from "@/features/chat/useCourseNames";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";
import { useWebSearchAvailability } from "@/features/chat/useWebSearchAvailability";
import { cn } from "@/lib/utils";

type ChatConversationViewProps = {
  sessionId: string;
  mode: ChatSession["mode"];
  title: string;
  hasCustomTitle: boolean;
  updatedAt: string;
  scope: ChatSession["scope"];
  courseId: string | null;
  recordId: string | null;
  recordDeleted: boolean;
  courseDeleted: boolean;
  libraryItemDeleted: boolean;
  messages: UseQueryResult<ChatMessage[]>;
  initialPrompt?: string;
};

/** 中栏对话区：标题栏 + 范围 chips + 建议卡 + 消息流 + 输入区。 */
export function ChatConversationView({
  sessionId,
  mode,
  title,
  hasCustomTitle,
  updatedAt,
  scope,
  courseId,
  recordId,
  recordDeleted,
  courseDeleted,
  libraryItemDeleted,
  messages,
  initialPrompt,
}: ChatConversationViewProps) {
  const { t, i18n } = useTranslation();
  const { isStreaming, streamedText, streamError, toolActivities, send, stop } =
    useChatStream(sessionId);
  const [composerValue, setComposerValue] = useState(initialPrompt ?? "");
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [recordPickOpen, setRecordPickOpen] = useState(false);
  const [coursePickOpen, setCoursePickOpen] = useState(false);
  const createSession = useCreateChatSession();
  const courseNames = useCourseNames();
  const favoriteSessionIds = useChatUiStore(
    (state) => state.favoriteSessionIds,
  );
  const toggleFavorite = useChatUiStore((state) => state.toggleFavorite);
  const research = mode === "RESEARCH";
  // 联网搜索开关按会话记忆；默认值研究会话恒 ON，普通会话按范围取
  // （自由 ON / 挂载类范围 OFF，B2 延伸）。
  const mountedScope = scope !== "FREE";
  const webSearchAvailable = useWebSearchAvailability();
  const webSearchEnabled = useChatUiStore((state) =>
    selectWebSearchEnabled(state, sessionId, mountedScope, research),
  );
  const setWebSearchEnabled = useChatUiStore(
    (state) => state.setWebSearchEnabled,
  );
  // 会话授权档位覆盖（工单 02）：显式拨过才随消息携带，未拨＝全局默认。
  const sessionAuthMode = useChatUiStore(
    (state) => state.authModeBySession[sessionId],
  );
  const scopeUnavailable = recordDeleted || courseDeleted || libraryItemDeleted;

  const visibleCount = (messages.data ?? []).filter(
    (message) => message.role !== "SYSTEM",
  ).length;
  const showSuggestions =
    !messages.isPending &&
    !messages.isError &&
    visibleCount === 0 &&
    streamedText === null &&
    !isStreaming &&
    !scopeUnavailable;
  const favorited = favoriteSessionIds.has(sessionId);

  function handleSelectScope(chip: ScopeChipId) {
    // 范围会话内不可变：点其它胶囊 = 发起对应范围的新会话（spec 根决策 2）。
    // LIBRARY_ITEM 无对应胶囊（仅资料详情入口创建），不会走到这里。
    if (chip === "libraryItem") return;
    if (chip === "course") {
      setCoursePickOpen(true);
      return;
    }
    if (chip === "record") {
      setRecordPickOpen(true);
      return;
    }
    createSession.mutate({
      mode: "ASK",
      scope: chip === "all" ? "ALL" : "FREE",
    });
  }

  const scopeBadge =
    scope === "COURSE" ? (
      <span className="bg-surface-subtle text-ink-muted flex items-center gap-1 rounded-xs px-1.5 py-px">
        <GraduationCap aria-hidden="true" className="size-3" />
        {courseNames.get(courseId ?? "") ?? t("chat.scope.course")}
      </span>
    ) : scope === "ALL" ? (
      <span className="bg-surface-subtle text-ink-muted flex items-center gap-1 rounded-xs px-1.5 py-px">
        <Library aria-hidden="true" className="size-3" />
        {t("chat.scope.all")}
      </span>
    ) : scope === "LIBRARY_ITEM" ? (
      <span className="bg-surface-subtle text-ink-muted flex items-center gap-1 rounded-xs px-1.5 py-px">
        <BookOpen aria-hidden="true" className="size-3" />
        {t("chat.scope.libraryItem")}
      </span>
    ) : null;
  const researchBadge = research ? (
    <span className="bg-chat-accent-soft text-chat-accent flex items-center gap-1 rounded-xs px-1.5 py-px">
      <Telescope aria-hidden="true" className="size-3" />
      {t("chat.badge.research")}
    </span>
  ) : null;

  return (
    <article
      aria-label={t("chat.detailLabel", { title })}
      className="flex h-full min-h-0 flex-col"
    >
      <header className="flex shrink-0 items-start gap-3 px-6 pt-6">
        <div className="min-w-0 flex-1">
          <h1
            className="text-headline font-headline text-ink-strong break-words"
            title={title}
          >
            {title}
          </h1>
          <p className="text-label text-muted-foreground mt-1 flex flex-wrap items-center gap-1.5">
            {recordDeleted ? (
              <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                {t("chat.recordDeleted")}
              </span>
            ) : null}
            {courseDeleted ? (
              <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                {t("chat.courseDeleted")}
              </span>
            ) : null}
            {libraryItemDeleted ? (
              <span className="bg-destructive/10 text-destructive rounded-xs px-1.5 py-px">
                {t("chat.libraryItemDeleted")}
              </span>
            ) : null}
            {researchBadge}
            {scopeBadge}
            {formatChatTimestamp(t, i18n.language, updatedAt)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-0.5 pt-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-pressed={favorited}
            aria-label={
              favorited ? t("chat.menu.unfavorite") : t("chat.menu.favorite")
            }
            onClick={() => toggleFavorite(sessionId)}
          >
            <Star
              aria-hidden="true"
              className={cn(favorited && "fill-chat-accent text-chat-accent")}
            />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("chat.menu.action", { title })}
                />
              }
            >
              <MoreHorizontal aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
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
      </header>

      <div className="shrink-0 px-6 pt-4">
        <ChatScopeChips
          scope={scope}
          onSelectScope={handleSelectScope}
          disabled={createSession.isPending}
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-6">
        {showSuggestions ? (
          <ChatSuggestions onPick={setComposerValue} research={research} />
        ) : null}
        {messages.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex flex-1 items-start gap-2 pt-6"
          >
            <Spinner aria-hidden="true" />
            {t("chat.loading")}
          </p>
        ) : messages.isError ? (
          <div className="flex-1 pt-6">
            <Alert variant="destructive">
              <AlertDescription>{messages.error.message}</AlertDescription>
            </Alert>
          </div>
        ) : (
          <ChatMessageList
            messages={messages.data}
            streamingText={streamedText}
            toolActivities={toolActivities}
            isStreaming={isStreaming}
            streamError={streamError}
            onRetry={(content) =>
              send(content, webSearchEnabled, sessionAuthMode)
            }
            showEmptyHint={!showSuggestions}
            sessionId={sessionId}
            defaultRecordId={recordId}
          />
        )}
        {/* MEMORY 提案就地确认卡（工单 06）：done 后出现，确认/拒绝即定局；
            本轮注入记忆的展示在右栏上下文面板。 */}
        <ChatMemoryProposalCard sessionId={sessionId} />
        {/* 入库提案就地确认卡（研究会话 V1）：逐条确认/拒绝，确认后走现有
            网页入库链路；本轮展示为临时态，提案本体跨重启持久。 */}
        <ChatResearchProposalCard sessionId={sessionId} />
        {/* 课程创建提案就地确认卡（通用 Agent 工单 02）：完整参数预览，确认后
            真实创建课程并转回执态；断线/重启经提案查询恢复。 */}
        <ChatOperationProposalCard sessionId={sessionId} />
        {/* 直执行回执卡（通用 Agent 第二阶段工单 02）：自动档免确认执行的
            操作呈现授权依据；断线/重启经 operation 查询恢复，清理后降级占位。 */}
        <ChatExecutedOperationCard sessionId={sessionId} />
        <ChatComposer
          value={composerValue}
          disabled={messages.isPending || scopeUnavailable}
          disabledHint={
            recordDeleted
              ? t("chat.composer.recordDeletedHint")
              : courseDeleted
                ? t("chat.composer.courseDeletedHint")
                : libraryItemDeleted
                  ? t("chat.composer.libraryItemDeletedHint")
                  : undefined
          }
          isStreaming={isStreaming}
          webSearchEnabled={webSearchEnabled}
          webSearchAvailable={webSearchAvailable}
          onToggleWebSearch={(next) => setWebSearchEnabled(sessionId, next)}
          onValueChange={setComposerValue}
          onSend={(content) => send(content, webSearchEnabled, sessionAuthMode)}
          onStop={stop}
        />
      </div>

      <RenameChatDialog
        sessionId={sessionId}
        displayTitle={title}
        hasCustomTitle={hasCustomTitle}
        open={renameOpen}
        onOpenChange={setRenameOpen}
      />
      <DeleteChatDialog
        sessionId={sessionId}
        title={title}
        wasActive
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
      <RecordMountDialog
        open={recordPickOpen}
        onOpenChange={setRecordPickOpen}
      />
      <CoursePickerDialog
        open={coursePickOpen}
        onOpenChange={setCoursePickOpen}
        pending={createSession.isPending}
        error={createSession.error?.message ?? null}
        onConfirm={(pickedCourseId) =>
          createSession.mutate({
            mode: "ASK",
            scope: "COURSE",
            course_id: pickedCourseId,
          })
        }
      />
    </article>
  );
}
