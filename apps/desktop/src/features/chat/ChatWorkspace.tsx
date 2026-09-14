import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from "@/components/ui/empty";
import { ProviderSetupGuide } from "@/components/common/ProviderSetupGuide";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatCitation, ChatMessage } from "@/features/chat/api/types";
import { ChatContextPanel } from "@/features/chat/ChatContextPanel";
import { ChatConversationView } from "@/features/chat/ChatConversationView";
import { ChatSessionSidebar } from "@/features/chat/ChatSessionSidebar";
import { NewChatButton } from "@/features/chat/NewChatButton";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { ApiError } from "@/services/http/client";

type ChatWorkspaceProps = {
  sessionId?: string;
  initialPrompt?: string;
};

/** AI 对话三栏工作区：对话记录 | 对话 | 上下文面板。 */
export function ChatWorkspace({
  sessionId,
  initialPrompt,
}: ChatWorkspaceProps) {
  const { t } = useTranslation();
  const sessions = useQuery({
    queryKey: chatKeys.list(),
    queryFn: () => chatApi.list(),
  });
  const detail = useQuery({
    queryKey: chatKeys.detail(sessionId ?? ""),
    queryFn: () => chatApi.get(sessionId ?? ""),
    enabled: sessionId !== undefined,
  });
  const messages = useQuery({
    queryKey: chatKeys.messages(sessionId ?? ""),
    queryFn: () => chatApi.getMessages(sessionId ?? ""),
    enabled: sessionId !== undefined,
  });
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: () => settingsApi.getLlmProvider(),
  });
  const providerReady =
    provider.data?.provider != null && provider.data.provider.has_api_key;

  const citations = collectCitations(messages.data ?? []);

  return (
    <section className="flex h-full min-h-0">
      <ChatSessionSidebar sessions={sessions} activeSessionId={sessionId} />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {sessionId === undefined ? (
          <ChatWelcome hasSessions={(sessions.data?.length ?? 0) > 0} />
        ) : detail.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground flex items-center gap-2 px-6 py-8"
          >
            <Spinner aria-hidden="true" />
            {t("chat.loading")}
          </p>
        ) : detail.isError ? (
          detail.error instanceof ApiError && detail.error.status === 404 ? (
            <div className="px-6 py-8">
              <Empty className="border-border items-start rounded-none border-t p-0 pt-8 text-start">
                <EmptyHeader className="items-start text-start">
                  <h2 className="text-section font-section text-ink">
                    {t("chat.notFoundTitle")}
                  </h2>
                  <EmptyDescription className="max-w-reading text-body text-start">
                    {t("chat.notFoundDescription")}
                  </EmptyDescription>
                </EmptyHeader>
                <Link
                  to="/chat"
                  className="text-body text-primary hover:text-primary-hover focus-visible:ring-ring/40 rounded-sm focus-visible:ring-3"
                >
                  {t("chat.backToList")}
                </Link>
              </Empty>
            </div>
          ) : (
            <div role="alert" className="px-6 py-8">
              <h2 className="text-section font-section text-ink">
                {t("chat.errorTitle")}
              </h2>
              <p className="max-w-reading text-body text-muted-foreground mt-2">
                {detail.error.message}
              </p>
              <Button
                variant="outline"
                className="mt-5"
                onClick={() => void detail.refetch()}
              >
                {t("chat.retry")}
              </Button>
            </div>
          )
        ) : provider.isPending ? null : !providerReady ? (
          <div className="flex min-h-0 flex-1 items-start overflow-y-auto px-6 py-8">
            <ProviderSetupGuide />
          </div>
        ) : (
          <ChatConversationView
            key={sessionId}
            sessionId={sessionId}
            title={detail.data.title ?? t("chat.untitled")}
            hasCustomTitle={detail.data.title !== null}
            updatedAt={detail.data.updated_at}
            scope={detail.data.scope}
            courseId={detail.data.course_id ?? null}
            recordDeleted={detail.data.record_deleted}
            courseDeleted={detail.data.course_deleted}
            messages={messages}
            initialPrompt={initialPrompt}
          />
        )}
      </div>

      {sessionId !== undefined ? (
        <ChatContextPanel
          sessionId={sessionId}
          scope={detail.data?.scope ?? "FREE"}
          recordId={detail.data?.record_id ?? null}
          courseId={detail.data?.course_id ?? null}
          recordDeleted={detail.data?.record_deleted ?? false}
          courseDeleted={detail.data?.course_deleted ?? false}
          citations={citations}
        />
      ) : null}
    </section>
  );
}

/** 右栏「来源引用」聚合当前对话的全部引用，按角标编号去重（后出现的回答优先）。 */
function collectCitations(messages: ChatMessage[]): ChatCitation[] {
  const byIndex = new Map<number, ChatCitation>();
  for (const message of messages) {
    if (message.role !== "ASSISTANT") continue;
    for (const citation of message.citations ?? []) {
      byIndex.set(citation.index, citation);
    }
  }
  return [...byIndex.values()].sort((left, right) => left.index - right.index);
}

function ChatWelcome({ hasSessions }: { hasSessions: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full items-center justify-center overflow-y-auto px-6 py-8">
      {hasSessions ? (
        <div className="text-center">
          <p className="text-section font-section text-ink">
            {t("chat.selectSessionTitle")}
          </p>
          <p className="text-body text-muted-foreground mt-2">
            {t("chat.selectSessionDescription")}
          </p>
          <div className="mt-5">
            <NewChatButton />
          </div>
        </div>
      ) : (
        <Empty className="border-border max-w-reading items-start rounded-none border-t p-0 pt-8 text-start">
          <EmptyHeader className="items-start text-start">
            <EmptyMedia className="justify-start">
              <Bot
                aria-hidden="true"
                className="text-muted-foreground size-8"
              />
            </EmptyMedia>
            <h2 className="text-section font-section text-ink">
              {t("chat.emptyTitle")}
            </h2>
            <EmptyDescription className="max-w-reading text-body text-start">
              {t("chat.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
          <div className="w-full items-start">
            <NewChatButton labelKey="chat.emptyAction" variant="outline" />
          </div>
        </Empty>
      )}
    </div>
  );
}
