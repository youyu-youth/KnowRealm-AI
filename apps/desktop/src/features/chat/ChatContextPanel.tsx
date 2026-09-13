import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import {
  BookOpenText,
  Code2,
  FileText,
  Globe,
  Lightbulb,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatCitation } from "@/features/chat/api/types";
import { ChatCitationList } from "@/features/chat/ChatCitationList";
import {
  CHAT_TOOL_IDS,
  useChatUiStore,
  type ChatToolId,
} from "@/features/chat/chatUiStore";

const TOOL_ICONS: Record<ChatToolId, typeof Globe> = {
  webSearch: Globe,
  knowledgeBase: BookOpenText,
  codeRun: Code2,
  documentParse: FileText,
};

type ChatContextPanelProps = {
  recordId: string | null;
  recordDeleted: boolean;
  citations: ChatCitation[];
};

/**
 * 右栏上下文面板：当前挂载内容（真实）、来源引用（真实）与工具状态（图 1 示意，
 * 开关只改本地状态，不触发任何请求）。
 */
export function ChatContextPanel({
  recordId,
  recordDeleted,
  citations,
}: ChatContextPanelProps) {
  const { t } = useTranslation();
  const tools = useChatUiStore((state) => state.tools);
  const toggleTool = useChatUiStore((state) => state.toggleTool);
  // 挂载记录的标题来自可挂载记录列表；与新建对话共用缓存。
  const recordOptions = useQuery({
    queryKey: chatKeys.recordOptions(),
    queryFn: () => chatApi.recordOptions(),
    enabled: recordId !== null,
  });
  const recordTitle =
    recordId === null
      ? null
      : (recordOptions.data?.find((record) => record.id === recordId)?.title ??
        null);

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
        {recordId === null ? (
          <p className="border-border-subtle text-label text-muted-foreground mt-3 rounded-lg border border-dashed px-3 py-3">
            {t("chat.context.free")}
          </p>
        ) : (
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
          {CHAT_TOOL_IDS.map((id) => {
            const Icon = TOOL_ICONS[id];
            return (
              <li key={id} className="flex items-center gap-3">
                <span className="bg-surface-subtle flex size-8 shrink-0 items-center justify-center rounded-md">
                  <Icon className="text-ink-muted size-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-body-dense text-ink flex items-center gap-1.5 font-medium">
                    {t(`chat.tools.${id}.title`)}
                    {id === "codeRun" ? (
                      <span className="bg-chat-accent-soft text-chat-accent text-label rounded-xs px-1.5 font-semibold">
                        {t("chat.tools.beta")}
                      </span>
                    ) : null}
                  </span>
                  <span className="text-label text-muted-foreground block">
                    {t(`chat.tools.${id}.description`)}
                  </span>
                </span>
                <Switch
                  size="sm"
                  checked={tools[id]}
                  onCheckedChange={() => toggleTool(id)}
                  aria-label={t(`chat.tools.${id}.title`)}
                  className="data-checked:bg-chat-accent"
                />
              </li>
            );
          })}
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
