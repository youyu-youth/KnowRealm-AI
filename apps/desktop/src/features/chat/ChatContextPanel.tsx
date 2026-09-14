import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  BookOpenText,
  Code2,
  FileText,
  Globe,
  GraduationCap,
  Lightbulb,
  Library,
  Plus,
} from "lucide-react";
import { AppTooltip } from "@/components/common/AppTooltip";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatCitation, ChatSession } from "@/features/chat/api/types";
import { ChatCitationList } from "@/features/chat/ChatCitationList";
import {
  CHAT_DEMO_TOOL_IDS,
  selectWebSearchEnabled,
  useChatUiStore,
  type ChatToolId,
} from "@/features/chat/chatUiStore";
import { useCourseNames } from "@/features/chat/useCourseNames";
import { useWebSearchAvailability } from "@/features/chat/useWebSearchAvailability";

const TOOL_ICONS: Record<ChatToolId, typeof Globe> = {
  webSearch: Globe,
  knowledgeBase: BookOpenText,
  codeRun: Code2,
  documentParse: FileText,
};

type ChatContextPanelProps = {
  sessionId: string;
  scope: ChatSession["scope"];
  recordId: string | null;
  courseId: string | null;
  recordDeleted: boolean;
  courseDeleted: boolean;
  citations: ChatCitation[];
};

/**
 * 右栏上下文面板：当前挂载内容（真实，按 scope 展示）、来源引用（真实，含 web 外链）
 * 与工具状态。联网搜索开关已接真（按会话记忆、发消息携带标志），其余三个为图 1 示意开关。
 */
export function ChatContextPanel({
  sessionId,
  scope,
  recordId,
  courseId,
  recordDeleted,
  courseDeleted,
  citations,
}: ChatContextPanelProps) {
  const { t } = useTranslation();
  const tools = useChatUiStore((state) => state.tools);
  const toggleTool = useChatUiStore((state) => state.toggleTool);
  const mountedScope = scope !== "FREE";
  const webSearchOn = useChatUiStore((state) =>
    selectWebSearchEnabled(state, sessionId, mountedScope),
  );
  const setWebSearchEnabled = useChatUiStore(
    (state) => state.setWebSearchEnabled,
  );
  const webSearchAvailable = useWebSearchAvailability();
  const courseNames = useCourseNames();
  // 挂载记录标题与范围记录数共用可挂载记录列表缓存；课程 / 全部范围也消费计数。
  const recordOptions = useQuery({
    queryKey: chatKeys.recordOptions(),
    queryFn: () => chatApi.recordOptions(),
    enabled: scope !== "FREE",
  });
  const recordTitle =
    recordId === null
      ? null
      : (recordOptions.data?.find((record) => record.id === recordId)?.title ??
        null);
  const scopeRecordCount =
    scope === "COURSE"
      ? recordOptions.data?.filter((record) => record.course_id === courseId)
          .length
      : recordOptions.data?.length;

  return (
    <aside
      className="border-border-subtle max-data:hidden flex w-80 shrink-0 flex-col overflow-y-auto border-l"
      aria-label={t("chat.context.label")}
    >
      <section className="px-5 pt-6">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-section font-section text-ink-strong">
            {t("chat.context.title")}
          </h2>
          {recordId !== null ? (
            <Link
              to="/records/$recordId"
              params={{ recordId }}
              search={{ tab: "transcript" }}
              className="text-label text-chat-accent hover:underline"
            >
              {t("chat.context.manage")}
            </Link>
          ) : null}
        </div>
        {scope === "FREE" ? (
          <p className="border-border-subtle text-label text-muted-foreground mt-3 rounded-lg border border-dashed px-3 py-3">
            {t("chat.context.free")}
          </p>
        ) : scope === "RECORD" ? (
          <div className="border-border-subtle bg-surface-subtle mt-3 flex items-start gap-3 rounded-lg border p-3">
            <span className="bg-surface-raised flex size-8 shrink-0 items-center justify-center rounded-md">
              <FileText className="text-ink-muted size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className="text-body-dense text-ink truncate font-medium"
                title={recordTitle ?? undefined}
              >
                {recordTitle ?? t("chat.context.recordFallback")}
              </p>
              <p className="text-label text-muted-foreground mt-0.5">
                {recordDeleted
                  ? t("chat.recordDeleted")
                  : t("chat.citation.recordTag")}
              </p>
            </div>
          </div>
        ) : (
          <div className="border-border-subtle bg-surface-subtle mt-3 flex items-start gap-3 rounded-lg border p-3">
            <span className="bg-surface-raised flex size-8 shrink-0 items-center justify-center rounded-md">
              {scope === "COURSE" ? (
                <GraduationCap
                  className="text-ink-muted size-4"
                  aria-hidden="true"
                />
              ) : (
                <Library className="text-ink-muted size-4" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className="text-body-dense text-ink truncate font-medium"
                title={
                  scope === "COURSE"
                    ? (courseNames.get(courseId ?? "") ?? undefined)
                    : undefined
                }
              >
                {scope === "COURSE"
                  ? (courseNames.get(courseId ?? "") ?? t("chat.scope.course"))
                  : t("chat.scope.all")}
              </p>
              <p className="text-label text-muted-foreground mt-0.5">
                {courseDeleted
                  ? t("chat.courseDeleted")
                  : t("chat.context.scopeRecords", {
                      count: scopeRecordCount ?? 0,
                    })}
              </p>
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          disabled
          className="text-muted-foreground mt-2 w-full justify-start"
        >
          <Plus data-icon="inline-start" aria-hidden="true" />
          {t("chat.context.addMore")}
        </Button>
      </section>

      <section className="px-5 pt-6">
        <h2 className="text-section font-section text-ink-strong">
          {t("chat.context.citations")}
        </h2>
        {citations.length > 0 ? (
          <div className="-mx-2 mt-2">
            <ChatCitationList citations={citations} />
          </div>
        ) : (
          <p className="text-label text-muted-foreground mt-3">
            {t("chat.context.citationsEmpty")}
          </p>
        )}
      </section>

      <section className="px-5 pt-6">
        <h2 className="text-section font-section text-ink-strong">
          {t("chat.tools.title")}
        </h2>
        <ul className="mt-3 flex flex-col gap-3.5">
          <ChatToolRow
            id="webSearch"
            label={t("chat.tools.webSearch.title")}
            description={t("chat.tools.webSearch.description")}
            control={
              webSearchAvailable ? (
                <Switch
                  size="sm"
                  checked={webSearchOn}
                  onCheckedChange={(checked) =>
                    setWebSearchEnabled(sessionId, checked)
                  }
                  aria-label={t("chat.tools.webSearch.title")}
                  className="data-checked:bg-chat-accent"
                />
              ) : (
                <AppTooltip
                  label={t("chat.tools.webSearch.unavailable")}
                  side="left"
                >
                  <span className="flex items-center">
                    <Switch
                      size="sm"
                      disabled
                      aria-label={t("chat.tools.webSearch.title")}
                      className="data-checked:bg-chat-accent"
                    />
                  </span>
                </AppTooltip>
              )
            }
          />
          {CHAT_DEMO_TOOL_IDS.map((id) => (
            <ChatToolRow
              key={id}
              id={id}
              label={t(`chat.tools.${id}.title`)}
              description={t(`chat.tools.${id}.description`)}
              badge={id === "codeRun" ? t("chat.tools.beta") : undefined}
              control={
                <Switch
                  size="sm"
                  checked={tools[id]}
                  onCheckedChange={() => toggleTool(id)}
                  aria-label={t(`chat.tools.${id}.title`)}
                  className="data-checked:bg-chat-accent"
                />
              }
            />
          ))}
        </ul>
      </section>

      <section className="px-5 py-6">
        <div className="bg-chat-accent-soft rounded-xl p-4">
          <p className="text-body-dense text-ink flex items-center gap-1.5 font-medium">
            <Lightbulb className="text-chat-accent size-4" aria-hidden="true" />
            {t("chat.tips.title")}
          </p>
          <p className="text-label text-ink-neutral mt-2 leading-relaxed">
            {t("chat.tips.body")}
          </p>
        </div>
      </section>
    </aside>
  );
}

type ChatToolRowProps = {
  id: ChatToolId;
  label: string;
  description: string;
  /** 角标文案（如 codeRun 的 Beta）。 */
  badge?: string;
  control: ReactNode;
};

function ChatToolRow({
  id,
  label,
  description,
  badge,
  control,
}: ChatToolRowProps) {
  const Icon = TOOL_ICONS[id];
  return (
    <li className="flex items-center gap-3">
      <span className="bg-surface-subtle flex size-8 shrink-0 items-center justify-center rounded-md">
        <Icon className="text-ink-muted size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="text-body-dense text-ink flex items-center gap-1.5 font-medium">
          {label}
          {badge ? (
            <span className="bg-chat-accent-soft text-chat-accent text-label rounded-xs px-1.5 font-semibold">
              {badge}
            </span>
          ) : null}
        </span>
        <span className="text-label text-muted-foreground block">
          {description}
        </span>
      </span>
      {control}
    </li>
  );
}
