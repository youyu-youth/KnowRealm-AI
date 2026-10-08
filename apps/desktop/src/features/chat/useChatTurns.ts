import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { AuthMode } from "@/features/agent/api/authMode";
import { agentKeys } from "@/features/agent/api/authMode";
import { chatApi } from "@/features/chat/api/chatSessions";
import type { ChatResponseProcess, ChatTurn } from "@/features/chat/api/types";
import { chatKeys } from "@/features/chat/api/keys";
import { libraryKeys } from "@/features/library/api/keys";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { ApiError } from "@/services/http/client";
import { derivePageSnapshot } from "@/features/chat/pageSnapshot";

/** 轮次终态判定（QUEUED、RUNNING、WAITING 系、INTERRUPTED 均为在途或可处理）。 */
const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

/** 订阅断线后的重连上限（超过后停止重连并按快照展示；用户可刷新恢复）。 */
const MAX_RECONNECT_ATTEMPTS = 8;

function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** 观察侧终态（含 INTERRUPTED）：订阅在此口径收尾；INTERRUPTED 仍占用会话
 * （新问前须停止），与提交闸门口径（isTerminal）分离。 */
const OBSERVER_TERMINAL_STATUSES = new Set([
  ...TERMINAL_STATUSES,
  "INTERRUPTED",
]);

function isObserverTerminal(status: string): boolean {
  return OBSERVER_TERMINAL_STATUSES.has(status);
}

/**
 * ChatTurn 提交 / 订阅 / 停止（切换会话不中断任务，票 01）。
 *
 * - 发送：提交轮次（202 立即返回）并从快照游标订阅持久事件；request_id 在
 *   未确认受理前保持稳定（网络重试不重复创建）。
 * - 切换 / 卸载 / 刷新：只关闭订阅（AbortController 管连接，不作业务停止），
 *   返回会话时从活动轮次快照恢复部分输出并续订。
 * - 停止：发持久取消指令；在途执行侧落实（cancel_requested＝「正在停止」）。
 * - 完成：done 事件为权威最终快照；历史经消息查询合并（不重复拼接 token）。
 */
export function useChatTurns(sessionId: string) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [turn, setTurn] = useState<ChatTurn | null>(null);
  const [streamedText, setStreamedText] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [responseProcess, setResponseProcess] =
    useState<ChatResponseProcess | null>(null);
  const segmentsRef = useRef(new Map<string, string>());
  const commentaryRef = useRef(new Set<string>());
  const abortRef = useRef<AbortController | null>(null);
  // 一次逻辑提交的稳定受理身份：确认受理（202）前网络重试复用。
  const pendingRequestIdRef = useRef<string | null>(null);
  // 当前订阅的轮次身份：防止迟到的旧订阅写回新轮次状态。
  const activeTurnIdRef = useRef<string | null>(null);
  // 本轮学习者记忆（工单 06）放 chatUiStore：消息流确认卡与右栏注入展示
  // 分属不同组件层，done 写入 / 发送与停止时清除（当轮语义，不落库）。
  const setTurnMemory = useChatUiStore((state) => state.setTurnMemory);
  const clearTurnMemory = useChatUiStore((state) => state.clearTurnMemory);

  const isStreaming = turn !== null && !isTerminal(turn.status);
  const stopping = isStreaming && turn.cancel_requested;

  useEffect(() => {
    // 切换会话或卸载只关闭订阅：后端继续执行，返回时经活动轮次恢复。
    return () => abortRef.current?.abort();
  }, [sessionId]);

  const clearTransientState = useCallback(() => {
    setStreamedText(null);
    segmentsRef.current.clear();
    commentaryRef.current.clear();
  }, []);

  const joinSegments = useCallback(() => {
    return [...segmentsRef.current]
      .filter(([id]) => !commentaryRef.current.has(id))
      .map(([, text]) => text)
      .join("");
  }, []);

  const invalidateTurnSideEffects = useCallback(() => {
    // 全部流结束路径统一失效提案 / 直执行 / 任务 / 共享引用查询（工单 02/05
    // 先例）：断开仅停止接收，已落库的提案与回执经查询恢复。
    void queryClient.invalidateQueries({
      queryKey: [...libraryKeys.all, "proposals"],
    });
    void queryClient.invalidateQueries({
      queryKey: agentKeys.sessionOperations(sessionId),
    });
    void queryClient.invalidateQueries({ queryKey: agentKeys.runs() });
    void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
    void queryClient.invalidateQueries({
      queryKey: chatKeys.messages(sessionId),
    });
  }, [queryClient, sessionId]);

  const finalizeCompleted = useCallback(
    async (content: string) => {
      // 权威最终正文以 done 事件为准（引用已在服务端解析）；随后重取消息
      // 历史（assistant 行）、会话列表（活跃度）与会话详情（标题更新）。
      setStreamedText(content);
      await queryClient.invalidateQueries({
        queryKey: chatKeys.messages(sessionId),
      });
      clearTransientState();
      setTurn(null);
      await queryClient.invalidateQueries({
        queryKey: chatKeys.detail(sessionId),
      });
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      invalidateTurnSideEffects();
    },
    [clearTransientState, invalidateTurnSideEffects, queryClient, sessionId],
  );

  const finalizeStalled = useCallback(
    async (turnId: string) => {
      // 终态但未见 done（取消 / 中断 / 快照对账发现）。取消对齐旧停止 UX：
      // 丢弃半截文本、末尾未回复提问露出「重新生成」；中断保留部分输出
      // （回到会话仍可看到已生成内容）。
      const snapshot = await chatApi.getTurn(turnId).catch(() => null);
      if (snapshot && isObserverTerminal(snapshot.status)) {
        setTurn(snapshot);
        if (snapshot.process) setResponseProcess(snapshot.process);
        if (snapshot.status === "FAILED") {
          setStreamError(snapshot.error_message || t("chat.turn.failed"));
          clearTransientState();
        } else if (snapshot.status === "CANCELLED") {
          setStreamError(null);
          clearTransientState();
        } else if (snapshot.status === "INTERRUPTED") {
          // 中断原因呈现（票边界：原会话可查看原因并停止，无继续按钮）。
          setStreamError(null);
          clearTransientState();
          setStreamedText(snapshot.output_text || "");
          setStreamError(t("chat.turn.interrupted"));
        } else {
          setStreamError(null);
          clearTransientState();
          setStreamedText(snapshot.output_text || "");
        }
        invalidateTurnSideEffects();
        void queryClient.invalidateQueries({
          queryKey: chatKeys.messages(sessionId),
        });
        return;
      }
    },
    [clearTransientState, invalidateTurnSideEffects, queryClient, sessionId, t],
  );

  /** 从 afterSeq 订阅轮次事件直到终态；异常断开时快照对账后重连。 */
  const observeTurn = useCallback(
    async (turnId: string, afterSeq: number, signal: AbortSignal) => {
      let cursor = afterSeq;
      for (let attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt += 1) {
        let terminalSeen = false;
        try {
          await chatApi.turnEvents(
            turnId,
            cursor,
            {
              onStatus: (payload) => {
                if (payload.process) setResponseProcess(payload.process);
                if (payload.phase === "generating") {
                  void queryClient.invalidateQueries({
                    queryKey: chatKeys.messages(sessionId),
                  });
                }
                if (
                  payload.phase === "cancelled" ||
                  payload.phase === "interrupted"
                ) {
                  terminalSeen = true;
                  void finalizeStalled(turnId);
                }
              },
              onToken: (text, segmentId = "legacy") => {
                segmentsRef.current.set(
                  segmentId,
                  (segmentsRef.current.get(segmentId) ?? "") + text,
                );
                setStreamedText(joinSegments());
              },
              onToolCall: (payload) => {
                if (payload.segmentId)
                  commentaryRef.current.add(payload.segmentId);
                if (payload.process) setResponseProcess(payload.process);
                setStreamedText(joinSegments());
              },
              onToolResult: (payload) => {
                if (payload.process) setResponseProcess(payload.process);
              },
              onDone: async (payload) => {
                terminalSeen = true;
                setResponseProcess(payload.process ?? null);
                setTurnMemory({
                  sessionId,
                  memoryUsed: payload.memoryUsed ?? [],
                  proposals: payload.memoryProposals ?? [],
                  researchProposals: payload.researchProposals ?? [],
                });
                await finalizeCompleted(payload.content);
              },
              onError: (payload) => {
                terminalSeen = true;
                clearTransientState();
                setStreamError(payload.detail);
                setTurn(null);
                invalidateTurnSideEffects();
              },
            },
            signal,
          );
        } catch (error) {
          const aborted =
            typeof error === "object" &&
            error !== null &&
            (error as { name?: string }).name === "AbortError";
          if (aborted) {
            // 用户离开 / 卸载只断开订阅：仍失效一次提案查询（断线前已落库
            // 的提案经查询恢复，旧流式路径同口径）。
            invalidateTurnSideEffects();
            return;
          }
          // 网络失败：落入下方快照对账重连。
        }
        if (terminalSeen || signal.aborted) return;
        // 流关闭但未见终态事件：快照对账（完成／失败就地收尾，在途则续订）。
        const snapshot = await chatApi.getTurn(turnId).catch(() => null);
        if (activeTurnIdRef.current !== turnId) return;
        if (snapshot === null) {
          setStreamError(t("chat.turn.missing"));
          return;
        }
        if (isObserverTerminal(snapshot.status)) {
          if (snapshot.status === "COMPLETED") {
            await finalizeCompleted(snapshot.output_text || "");
          } else {
            await finalizeStalled(turnId);
          }
          return;
        }
        setTurn(snapshot);
        // 断线期间的 M+1..N 事件不再重放：以服务端快照正文为权威基准重置本地
        // 拼接（缺口同步，规格 §5），再从 last_seq 续订后续增量。
        segmentsRef.current.clear();
        commentaryRef.current.clear();
        setStreamedText(snapshot.output_text || "");
        if (snapshot.process) setResponseProcess(snapshot.process);
        cursor = snapshot.last_seq;
        await new Promise((resolve) =>
          setTimeout(resolve, 250 * (attempt + 1)),
        );
      }
      // 重连耗尽：保留已收内容并提示可刷新恢复（不弹通知，恢复只提示本会话）。
      setStreamError(t("chat.turn.disconnected"));
    },
    [
      clearTransientState,
      finalizeCompleted,
      finalizeStalled,
      invalidateTurnSideEffects,
      joinSegments,
      queryClient,
      sessionId,
      setTurnMemory,
      t,
    ],
  );

  const startObservation = useCallback(
    (turnId: string, afterSeq: number) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      activeTurnIdRef.current = turnId;
      void observeTurn(turnId, afterSeq, controller.signal).finally(() => {
        if (activeTurnIdRef.current === turnId) {
          activeTurnIdRef.current = null;
        }
      });
    },
    [observeTurn],
  );

  const hydrateSnapshot = useCallback((snapshot: ChatTurn) => {
    setTurn(snapshot);
    setStreamedText(snapshot.output_text || "");
    if (snapshot.process) setResponseProcess(snapshot.process);
    segmentsRef.current.clear();
    commentaryRef.current.clear();
  }, []);

  // 会话打开 / 返回 / 刷新：恢复在途轮次（部分输出 + 过程）并从游标续订。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const active = await chatApi.activeTurn(sessionId);
        if (cancelled || active === null || isTerminal(active.status)) return;
        hydrateSnapshot(active);
        startObservation(active.id, active.last_seq);
      } catch {
        // 活动轮次查询失败不打断会话打开（历史仍可读）。
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 会话身份级初始化
  }, [sessionId]);

  const send = useCallback(
    async (content: string, webSearch: boolean, authMode?: AuthMode) => {
      if (turn !== null && !isTerminal(turn.status)) return;
      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;
      setStreamError(null);
      setResponseProcess(null);
      setStreamedText("");
      segmentsRef.current.clear();
      commentaryRef.current.clear();
      clearTurnMemory(sessionId);
      const requestId = pendingRequestIdRef.current ?? crypto.randomUUID();
      pendingRequestIdRef.current = requestId;
      try {
        const snapshot = await chatApi.submitTurn(sessionId, {
          content,
          webSearch,
          requestId,
          page: derivePageSnapshot(),
          authMode,
        });
        pendingRequestIdRef.current = null;
        activeTurnIdRef.current = snapshot.id;
        hydrateSnapshot(snapshot);
        // 受理即失效消息查询：服务端已落 user 行（生成开始就显示提问，
        // 不等首个 token / done）。
        void queryClient.invalidateQueries({
          queryKey: chatKeys.messages(sessionId),
        });
        startObservation(snapshot.id, snapshot.last_seq);
      } catch (error) {
        // 受理结果未确认（网络失败，无 HTTP 响应）保留 request_id：同身份
        // 重试幂等返回原轮次（规格 §4）；拿到任何服务端裁决（含 409/422）
        // 即清除，避免用户改内容后撞旧身份指纹冲突。
        if (!(error instanceof ApiError)) {
          pendingRequestIdRef.current = requestId;
        } else {
          pendingRequestIdRef.current = null;
        }
        clearTransientState();
        setStreamError(error instanceof Error ? error.message : String(error));
      }
    },
    [
      clearTransientState,
      clearTurnMemory,
      hydrateSnapshot,
      queryClient,
      sessionId,
      startObservation,
      turn,
    ],
  );

  const stop = useCallback(() => {
    const current = turn;
    if (current === null || isTerminal(current.status)) return;
    void chatApi
      .cancelTurn(current.id)
      .then((result) => setTurn(result.turn))
      .catch(() => undefined);
  }, [turn]);

  return {
    isStreaming,
    stopping,
    turn,
    streamedText,
    streamError,
    responseProcess,
    send,
    stop,
  };
}
