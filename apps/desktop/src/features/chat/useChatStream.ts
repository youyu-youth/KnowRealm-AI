import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AuthMode } from "@/features/agent/api/authMode";
import { agentKeys } from "@/features/agent/api/authMode";
import { chatApi } from "@/features/chat/api/chatSessions";
import type { ChatResponseProcess } from "@/features/chat/api/types";
import { chatKeys } from "@/features/chat/api/keys";
import { libraryKeys } from "@/features/library/api/keys";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { derivePageSnapshot } from "@/features/chat/pageSnapshot";

export function useChatStream(sessionId: string) {
  const queryClient = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [responseProcess, setResponseProcess] =
    useState<ChatResponseProcess | null>(null);
  const segmentsRef = useRef(new Map<string, string>());
  const commentaryRef = useRef(new Set<string>());
  const abortRef = useRef<AbortController | null>(null);
  // 本轮学习者记忆（工单 06）放 chatUiStore：消息流确认卡与右栏注入展示
  // 分属不同组件层，done 写入 / 发送与停止时清除（当轮语义，不落库）。
  const setTurnMemory = useChatUiStore((state) => state.setTurnMemory);
  const clearTurnMemory = useChatUiStore((state) => state.clearTurnMemory);

  useEffect(() => {
    // 切换会话或卸载时中止在途流，防止连接泄漏与串会话渲染。
    return () => abortRef.current?.abort();
  }, [sessionId]);

  // 流式文本与工具过程卡同生命周期：一起置空即回到历史态。
  const clearTransientState = useCallback(() => {
    setStreamedText(null);
    segmentsRef.current.clear();
    commentaryRef.current.clear();
  }, []);

  const send = useCallback(
    (content: string, webSearch: boolean, authMode?: AuthMode) => {
      if (abortRef.current) return;
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStreamedText("");
      setStreamError(null);
      setResponseProcess(null);
      segmentsRef.current.clear();
      commentaryRef.current.clear();
      clearTurnMemory(sessionId);
      chatApi
        .streamMessage(
          sessionId,
          content,
          {
            onStatus: (payload) => {
              if (payload?.process) {
                setResponseProcess(payload.process);
                for (const entry of payload.process.entries ?? []) {
                  if (entry.kind === "commentary")
                    commentaryRef.current.add(entry.id);
                }
                setStreamedText(
                  [...segmentsRef.current]
                    .filter(([id]) => !commentaryRef.current.has(id))
                    .map(([, text]) => text)
                    .join(""),
                );
              }
              if (!payload || payload.phase === "generating") {
                setIsStreaming(true);
                void queryClient.invalidateQueries({
                  queryKey: chatKeys.messages(sessionId),
                });
              }
            },
            onToken: (text, segmentId = "legacy") => {
              segmentsRef.current.set(
                segmentId,
                (segmentsRef.current.get(segmentId) ?? "") + text,
              );
              setStreamedText(
                [...segmentsRef.current]
                  .filter(([id]) => !commentaryRef.current.has(id))
                  .map(([, value]) => value)
                  .join(""),
              );
            },
            onToolCall: (payload) => {
              if (payload.segmentId)
                commentaryRef.current.add(payload.segmentId);
              if (payload.process) setResponseProcess(payload.process);
              setStreamedText(
                [...segmentsRef.current]
                  .filter(([id]) => !commentaryRef.current.has(id))
                  .map(([, text]) => text)
                  .join(""),
              );
            },
            onToolResult: (payload) => {
              if (payload.process) setResponseProcess(payload.process);
            },
            onDone: async (payload) => {
              // 先清流式临时态（历史重取后消息由 REST 承载），再落本轮记忆展示
              // （done 载荷是本轮注入记忆与待确认提案的唯一来源）。
              setResponseProcess(payload.process ?? null);
              setStreamedText(payload.content);
              setTurnMemory({
                sessionId,
                memoryUsed: payload.memoryUsed ?? [],
                proposals: payload.memoryProposals ?? [],
                researchProposals: payload.researchProposals ?? [],
              });
              // 重取消息历史（assistant 行）、会话列表（活跃度排序）与会话详情
              // （首条消息后标题更新）；操作提案走提案查询恢复（服务端唯一事实源）。
              await queryClient.invalidateQueries({
                queryKey: chatKeys.messages(sessionId),
              });
              if (!abortRef.current || abortRef.current === controller)
                clearTransientState();
              await queryClient.invalidateQueries({
                queryKey: chatKeys.detail(sessionId),
              });
              await queryClient.invalidateQueries({
                queryKey: chatKeys.list(),
              });
            },
            onError: (payload) => {
              clearTransientState();
              if (payload.process) setResponseProcess(payload.process);
              setStreamError(payload.detail);
            },
          },
          controller.signal,
          webSearch,
          derivePageSnapshot(),
          authMode,
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
          // 全部流结束路径（done / SSE error / 停止 / 网络断开）统一失效提案
          // 查询（工单 02 review）：断开仅停止接收，已落库的提案经查询恢复；
          // 直执行回执（工单 02）同口径——免确认执行已生效，经 operation 查询
          // 恢复状态视图。
          void queryClient.invalidateQueries({
            queryKey: [...libraryKeys.all, "proposals"],
          });
          void queryClient.invalidateQueries({
            queryKey: agentKeys.sessionOperations(sessionId),
          });
          // 任务（run）查询同口径（工单 05）：批量计划卡 / 会话任务面板经持久化
          // 查询恢复——计划卡提案与直建 Run 都在本轮落库，流结束即拉最新。
          void queryClient.invalidateQueries({ queryKey: agentKeys.runs() });
          // 共享引用缓存同口径（工单 05）：自动档直执行的引用增删已生效，流中
          // 动作类型不可知——统一失效，挂载中的共享 Tab 随即重取。
          void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
          void queryClient.invalidateQueries({
            queryKey: chatKeys.messages(sessionId),
          });
          setResponseProcess((current) =>
            current?.status === "RUNNING"
              ? {
                  ...current,
                  status: "INTERRUPTED",
                  elapsed_ms: Math.max(
                    current.elapsed_ms ?? 0,
                    Date.now() - Date.parse(current.started_at),
                  ),
                  entries: (current.entries ?? []).map((entry) =>
                    entry.kind === "tool" && entry.status === "RUNNING"
                      ? { ...entry, status: "INTERRUPTED" }
                      : entry,
                  ),
                }
              : current,
          );
          abortRef.current = null;
          setIsStreaming(false);
        });
    },
    [
      clearTransientState,
      clearTurnMemory,
      queryClient,
      sessionId,
      setTurnMemory,
    ],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    isStreaming,
    streamedText,
    streamError,
    responseProcess,
    send,
    stop,
  };
}
