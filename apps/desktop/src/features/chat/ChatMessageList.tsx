import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, BookmarkPlus, RotateCcw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type {
  ChatMessage,
  ChatResponseProcess as Process,
} from "@/features/chat/api/types";
import { ChatMarkdown } from "@/features/chat/ChatMarkdown";
import {
  planDraftStreamingView,
  stripPlanDraftBlocks,
} from "@/features/chat/planDraftJson";
import { SaveKnowledgePointDialog } from "@/features/chat/SaveKnowledgePointDialog";
import { ChatResponseProcess } from "@/features/chat/ChatResponseProcess";
import { ChatTurnPartialOutput } from "@/features/chat/ChatTurnPartialOutput";

type ChatMessageListProps = {
  messages: ChatMessage[];
  streamingText: string | null;
  responseProcess?: Process | null;
  isStreaming: boolean;
  streamError: string | null;
  onRetry: (content: string) => void;
  /** 建议卡已承担空会话引导时置 false，避免重复文案。 */
  showEmptyHint?: boolean;
  /** 对话转知识点（对话转学习资产 V1）：保存对话框所需的会话标识。 */
  sessionId: string;
  /** RECORD 会话的挂载记录，作为保存目标默认值；其它范围为空。 */
  defaultRecordId: string | null;
};

const messageTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
});

/** 计划草案 JSON 折叠块（工单 02 真机验收兜底）：正文整体即草案 JSON 时
 * （模型未输出中文复述），以摘要行 + 可展开原始数据呈现并引导重新发起。 */
function PlanDraftJsonBlock({
  raw,
  itemCount,
}: {
  raw: string;
  itemCount: number;
}) {
  const { t } = useTranslation();
  return (
    <div className="bg-surface-subtle flex flex-col gap-1.5 rounded-md px-3 py-2">
      <p className="text-label text-ink">
        {t("chat.planDraftJson.summary", { count: itemCount })}
      </p>
      <p className="text-label text-muted-foreground">
        {t("chat.planDraftJson.hint")}
      </p>
      <details>
        <summary className="text-label text-muted-foreground cursor-pointer">
          {t("chat.planDraftJson.expand")}
        </summary>
        <pre className="text-label text-ink-muted mt-1.5 overflow-x-auto break-all whitespace-pre-wrap">
          {raw}
        </pre>
      </details>
    </div>
  );
}

export function ChatMessageList({
  messages,
  streamingText,
  responseProcess = null,
  isStreaming,
  streamError,
  onRetry,
  showEmptyHint = true,
  sessionId,
  defaultRecordId,
}: ChatMessageListProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const readingProcessRef = useRef(false);
  const [showJump, setShowJump] = useState(false);
  const [saveTarget, setSaveTarget] = useState<ChatMessage | null>(null);
  // SYSTEM 是会话创建时的角色快照，仅喂给模型，不渲染给用户。
  const visible = messages.filter((message) => message.role !== "SYSTEM");
  const lastVisible = visible[visible.length - 1];
  const interrupted =
    lastVisible !== undefined &&
    lastVisible.role === "USER" &&
    !isStreaming &&
    streamingText === null;

  useEffect(() => {
    const container = scrollRef.current;
    if (container && followRef.current && !readingProcessRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [visible.length, streamingText]);

  const allProcesses = visible.flatMap(
    (message) => message.response_processes ?? [],
  );
  const currentProcess =
    responseProcess &&
    allProcesses.find((process) => process.id === responseProcess.id);
  // REST 已有终态后优先用持久化事实；接收期间使用流快照。
  const liveProcess =
    currentProcess &&
    currentProcess.status !== "RUNNING" &&
    responseProcess?.history_saved !== false
      ? currentProcess
      : responseProcess;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto"
        aria-label={t("chat.process.conversation")}
        onScroll={(event) => {
          const element = event.currentTarget;
          followRef.current =
            element.scrollHeight - element.scrollTop - element.clientHeight <=
            80;
          setShowJump(!followRef.current);
        }}
        onClickCapture={(event) => {
          const target = event.target;
          if (
            target instanceof Element &&
            target.closest('[data-slot="collapsible"]')
          ) {
            readingProcessRef.current = true;
            followRef.current = false;
            setShowJump(true);
          }
        }}
      >
        {visible.length === 0 && streamingText === null ? (
          showEmptyHint ? (
            <p className="text-body text-muted-foreground py-8 text-center">
              {t("chat.emptyConversation")}
            </p>
          ) : null
        ) : (
          <ul className="flex flex-col gap-6 py-6">
            {visible.map((message) =>
              message.role === "USER" ? (
                <li key={message.id} className="flex min-w-0 flex-col gap-1">
                  <div className="flex flex-col items-end gap-1">
                    <p className="bg-primary text-primary-foreground text-body max-w-[85%] rounded-2xl rounded-ee-md px-4 py-2.5 break-words whitespace-pre-wrap">
                      {message.content}
                    </p>
                    <time
                      dateTime={message.created_at}
                      className="text-label text-muted-foreground px-1"
                    >
                      {messageTimeFormatter.format(
                        new Date(message.created_at),
                      )}
                    </time>
                  </div>
                  {(() => {
                    const processes = [...(message.response_processes ?? [])];
                    if (liveProcess?.user_message_id === message.id) {
                      const index = processes.findIndex(
                        (process) => process.id === liveProcess.id,
                      );
                      if (index >= 0) processes[index] = liveProcess;
                      else processes.push(liveProcess);
                    }
                    return processes.map((process) => (
                      <ChatResponseProcess key={process.id} process={process} />
                    ));
                  })()}
                  {/* 终态轮次的部分输出（规格 §5/§15）：按轮次引用恢复已持久化正文。 */}
                  <ChatTurnPartialOutput turn={message.turn} />
                </li>
              ) : (
                <li key={message.id} className="flex min-w-0 flex-col gap-3">
                  {(() => {
                    const stripped = stripPlanDraftBlocks(message.content);
                    if (stripped !== null && stripped.rest !== "") {
                      // 草案 JSON（任意位置）+ 中文复述：移除 JSON 段只渲染中文。
                      return (
                        <ChatMarkdown
                          content={stripped.rest}
                          citations={message.citations ?? []}
                        />
                      );
                    }
                    if (stripped !== null) {
                      return (
                        <PlanDraftJsonBlock
                          raw={stripped.blocks[0].json}
                          itemCount={stripped.blocks.reduce(
                            (total, block) => total + block.itemCount,
                            0,
                          )}
                        />
                      );
                    }
                    return (
                      <ChatMarkdown
                        content={message.content}
                        citations={message.citations ?? []}
                      />
                    );
                  })()}
                  {/* 对话转知识点（对话转学习资产 V1）：messages 里的回答均已落库，可直接保存。 */}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-ink h-auto w-fit cursor-pointer gap-1.5 px-2 py-1"
                    onClick={() => setSaveTarget(message)}
                  >
                    <BookmarkPlus
                      data-icon="inline-start"
                      aria-hidden="true"
                      className="size-3.5"
                    />
                    {t("chat.saveKp.action")}
                  </Button>
                </li>
              ),
            )}
            {streamingText !== null &&
            !visible.some(
              (message) => message.id === liveProcess?.assistant_message_id,
            ) ? (
              <li className="flex min-w-0 flex-col gap-3">
                {liveProcess &&
                !visible.some(
                  (message) => message.id === liveProcess.user_message_id,
                ) ? (
                  <ChatResponseProcess
                    key={liveProcess.id}
                    process={liveProcess}
                  />
                ) : null}
                {streamingText ? (
                  (() => {
                    const view = planDraftStreamingView(streamingText);
                    return view.kind === "pending" ? (
                      <p
                        role="status"
                        className="text-body text-muted-foreground animate-pulse"
                      >
                        {t("chat.planDraftJson.streaming")}
                      </p>
                    ) : (
                      <ChatMarkdown
                        content={view.text}
                        citations={[]}
                        streaming
                      />
                    );
                  })()
                ) : !liveProcess ? (
                  <p role="status" className="text-body text-muted-foreground">
                    {t("chat.streamingStatus")}
                  </p>
                ) : null}
              </li>
            ) : null}
          </ul>
        )}

        {streamError !== null ? (
          <Alert variant="destructive" className="mt-2">
            <AlertDescription>{streamError}</AlertDescription>
          </Alert>
        ) : null}

        {interrupted ? (
          <div className="border-border-subtle mt-4 flex flex-col gap-2 border-t pt-4">
            <p className="text-label text-muted-foreground">
              {t("chat.interruptedDescription")}
            </p>
            <div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRetry(lastVisible.content)}
              >
                <RotateCcw data-icon="inline-start" aria-hidden="true" />
                {t("chat.retryAnswer")}
              </Button>
            </div>
          </div>
        ) : null}
        <SaveKnowledgePointDialog
          message={saveTarget}
          onClose={() => setSaveTarget(null)}
          sessionId={sessionId}
          defaultRecordId={defaultRecordId}
        />
      </div>
      {showJump ? (
        <Button
          variant="outline"
          size="sm"
          className="absolute right-4 bottom-4 cursor-pointer max-md:right-1 max-md:bottom-1 max-md:size-6 max-md:p-0"
          onClick={() => {
            readingProcessRef.current = false;
            followRef.current = true;
            setShowJump(false);
            const container = scrollRef.current;
            if (container) container.scrollTop = container.scrollHeight;
          }}
        >
          <ArrowDown data-icon="inline-start" aria-hidden="true" />
          <span className="max-md:sr-only">
            {t("chat.process.jumpToLatest")}
          </span>
        </Button>
      ) : null}
    </div>
  );
}
