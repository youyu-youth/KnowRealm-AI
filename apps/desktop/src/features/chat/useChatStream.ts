import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";

/**
 * 单会话的流式回答状态：发送 / 停止 / 逐字渲染 / 检索过程 / done 后失效重取。
 * 流式文本与工具过程卡都是本组件树内的临时态，事实源始终是 chat_messages（REST）。
 */
export type ChatToolActivity = {
  tool: string;
  query: string;
  /** null = 检索进行中；非空 = 结果（命中数 + 是否成功）。 */
  result: { hits: number; ok: boolean } | null;
};

export function useChatStream(sessionId: string) {
  const queryClient = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [toolActivities, setToolActivities] = useState<ChatToolActivity[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // 切换会话或卸载时中止在途流，防止连接泄漏与串会话渲染。
    return () => abortRef.current?.abort();
  }, [sessionId]);

  // 流式文本与工具过程卡同生命周期：一起置空即回到历史态。
  const clearTransientState = useCallback(() => {
    setStreamedText(null);
    setToolActivities([]);
  }, []);

  const send = useCallback(
    (content: string, webSearch: boolean) => {
      if (abortRef.current) return;
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStreamedText("");
      setStreamError(null);
      setToolActivities([]);
      chatApi
        .streamMessage(
          sessionId,
          content,
          {
            onStatus: () => setIsStreaming(true),
            onToken: (text) =>
              setStreamedText((current) => (current ?? "") + text),
            onToolCall: (payload) =>
              setToolActivities((current) => [
                ...current,
                { tool: payload.tool, query: payload.query, result: null },
              ]),
            onToolResult: (payload) =>
              setToolActivities((current) => {
                // 工具循环逐次串行，结果只回填最后一张在途卡；无对应卡片时忽略。
                const last = current[current.length - 1];
                if (last === undefined || last.result !== null) return current;
                const next = [...current];
                next[next.length - 1] = {
                  ...last,
                  result: { hits: payload.hits, ok: payload.ok },
                };
                return next;
              }),
            onDone: async () => {
              clearTransientState();
              // 重取消息历史（assistant 行）、会话列表（活跃度排序）与会话详情（首条消息后标题更新）。
              await queryClient.invalidateQueries({
                queryKey: chatKeys.messages(sessionId),
              });
              await queryClient.invalidateQueries({
                queryKey: chatKeys.detail(sessionId),
              });
              await queryClient.invalidateQueries({
                queryKey: chatKeys.list(),
              });
            },
            onError: (payload) => {
              clearTransientState();
              setStreamError(payload.detail);
            },
          },
          controller.signal,
          webSearch,
        )
        .catch((error: unknown) => {
          // 用户停止属于预期路径，静默；其余（409 在途、网络失败等）展示可读错误。
          // AbortError 可能是 DOMException（非 Error 子类），只能按 name 斤断——故在此 as 收窄。
          const aborted =
            typeof error === "object" &&
            error !== null &&
            (error as { name?: string }).name === "AbortError";
          if (aborted) {
            // 停止/断开：丢弃半截文本，让历史末尾的未回复提问与“重新生成”入口露出。
            clearTransientState();
          } else {
            clearTransientState();
            setStreamError(
              error instanceof Error ? error.message : String(error),
            );
          }
        })
        .finally(() => {
          abortRef.current = null;
          setIsStreaming(false);
        });
    },
    [clearTransientState, queryClient, sessionId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { isStreaming, streamedText, streamError, toolActivities, send, stop };
}
