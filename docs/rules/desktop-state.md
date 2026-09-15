---
paths:
  - "apps/desktop/src/**"
---

# 规范：桌面端状态管理与通信

> 适用范围：`stores/`、`services/http/`、`services/tauri/` 及各 feature 的数据获取代码。

## 1. 数据所有权（写代码前先确认）

| 数据 | 唯一归属 |
|---|---|
| sidecar 拥有、可变化的业务数据 | TanStack Query v5（课程、记录、统计、AI 产出） |
| 当前窗口/本机会话状态 | Zustand v5（录音电平、播放进度、弹窗开关） |
| 可分享/可恢复的页面状态 | Router search params（筛选、分页、tab） |

- `knowrealm.db` 是业务事实源：前端不创建第二份持久化业务数据，不把服务端数据复制进 Zustand。
- 启动能力令牌只存在于类型化 sidecar 桥接与统一 HTTP 客户端，不进 Zustand、URL 或持久缓存。
- 技术线：`@tanstack/react-query` v5、Zustand v5、原生 `fetch` + `eventsource-parser`（不用停更的 `@microsoft/fetch-event-source`）。

## 2. TanStack Query v5

- 只用 v5 对象签名（加载态 `isPending`）；queryKey 工厂集中 `api/keys.ts`，资源与全部查询参数必须进 key；业务 API 按 `features/<feature>/api/` 组织。
- mutation 成功后精确失效受影响详情 key + 相关列表/聚合 key；简单可回滚编辑可乐观更新（带失败回滚），长流程（生成总结等）不乐观更新。
- 仅进程内缓存（staleTime 60s、retry 2、不 refetchOnWindowFocus），不用 `persistQueryClient`；录音崩溃恢复是 sidecar `recording_sessions` 的事实，不属于前端缓存。

## 3. Zustand v5

- store 只放客户端 state 和 action：服务端实体、能力令牌、定时器、事件监听不进 store。
- 字段 selector 最小订阅；多字段/派生对象用 `useShallow`；副作用放组件/hook 并在卸载时清理。
- `persist` 仅限需恢复的非业务客户端状态且 `partialize` 限字段；持久业务状态必须由 sidecar API 提供。

## 4. HTTP 与 SSE

- UI 与后端唯一通道 `services/http/client.ts`：统一 base URL、JSON 头、`X-KnowRealm-Token` 强制覆盖（调用方不能省略替换）；非 2xx 解析 `{"detail":...}` 抛 `ApiError`，feature API 不重复实现错误处理；`getSidecarConfig()` 只经类型化 Tauri bridge 取端口与令牌。
- SSE 统一原生 `fetch` 读流 + `eventsource-parser` 解析（原生 EventSource 无法带令牌头，不用）：AI 问答 POST 流；Record 失效通知 `GET /api/records/{record_id}/events`；连接携带令牌，卸载或用户停止时 `AbortController.abort()`。
- Chat 事件类型固定 `status`/`token`/`tool_call`/`tool_result`/`citation`/`interrupt`/`done`/`error`（ADR-0019；`interrupt` 当前尚未发出），必须显式处理 `error` 和 `done`；Record 事件只表达"该 Record 已变化"，不携带业务状态副本。
- 消费路径固定：queryKey 工厂定位缓存 → `invalidateQueries` → REST 重取；SSE 断线时仅非终态 Record 每 2 秒条件轮询，终态立即停止，不做事件重放。
