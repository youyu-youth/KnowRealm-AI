# 规范：桌面端状态管理与通信

> 适用范围：`stores/`、`services/http/`、`services/tauri/` 及各 feature 的数据获取代码。

## 1. 核心裁决

写代码前先确认数据所有者：

| 数据 | 唯一归属 | 典型内容 |
|---|---|---|
| sidecar 拥有、可变化的业务数据 | TanStack Query v5 | 课程、记录、统计、AI 产出 |
| 当前窗口或本机会话状态 | Zustand v5 | 录音电平、播放器进度、弹窗开关 |
| 可分享或可恢复的页面状态 | Router search params | 筛选、分页、tab |

- `knowrealm.db` 是业务事实源；前端不得创建第二份持久化业务数据，也不得把服务端数据复制进 Zustand。
- 本地单用户模式无登录会话。Tauri 壳生成的单次启动能力令牌只存在于类型化 sidecar 桥接与统一 HTTP 客户端，不进入 Zustand、URL 或持久缓存。
- 固定技术线：`@tanstack/react-query` v5、Zustand v5、原生 `fetch` + `eventsource-parser`；不使用停更的 `@microsoft/fetch-event-source`。

## 2. TanStack Query v5

### 2.1 查询与 Query Key

- 只使用 v5 对象签名；加载态使用 `isPending`，不新增位置参数调用或旧 `isLoading` 用法。
- 每个 feature 在 `api/keys.ts` 定义 queryKey 工厂。资源、列表/详情和所有查询参数必须进入 key，调用处不得手写散落 key。
- 所有 sidecar 数据通过 `useQuery` / `useMutation` 管理；业务 API 按 `features/<feature>/api/` 组织。

```ts
export const recordKeys = {
  all: ["records"] as const,
  list: (query: RecordListQuery) => [...recordKeys.all, "list", query] as const,
  detail: (id: string) => [...recordKeys.all, "detail", id] as const,
};
```

### 2.2 变更与刷新

- mutation 成功后必须精确失效受影响的详情 key，并失效相关列表或聚合 key。
- 简单、可回滚的编辑可用 `onMutate` 乐观更新，并保留失败回滚；生成总结等长流程不做乐观更新。
- sidecar 状态事件到达后只触发 `invalidateQueries`，由 Query 重取事实；SSE 回调不得直接维护业务数据副本。

### 2.3 缓存策略

桌面端仅使用进程内缓存。默认配置保持：

```ts
queries: {
  staleTime: 60_000,
  retry: 2,
  refetchOnWindowFocus: false,
}
```

- 不使用 `persistQueryClient`、`cached_*` 表或 `/api/sync`。sidecar 位于 127.0.0.1，重启后直接重新查询。
- 录音崩溃恢复属于 sidecar 的 `recording_sessions` 事实，不属于 Query 持久化或 Zustand 业务缓存。

## 3. Zustand v5

- store 只保存客户端 state 和 action；服务端实体、能力令牌、定时器和事件监听不得进入 store。
- 组件使用字段 selector 最小订阅；一次订阅多个字段或返回派生对象时使用 `useShallow`，避免整店订阅和无效重渲染。
- 定时器、订阅和其他副作用放在组件或 hook 中，并在卸载时清理。
- `persist` 仅可保存明确需要恢复的非业务客户端状态，并用 `partialize` 限定字段；持久业务状态必须由 sidecar API 提供。

## 4. 统一 HTTP 通道

- UI 与后端的唯一通道是 `services/http/client.ts`；禁止前端直连数据库或直接写业务数据。
- `getSidecarConfig()` 只能通过类型化 Tauri bridge 取得随机端口和单次启动能力令牌。
- 统一客户端负责 base URL、JSON 头、错误类型和 `X-KnowRealm-Token`。令牌头必须强制覆盖，调用方不能省略或替换。
- 非 2xx 响应统一解析 `{"detail": ...}` 并抛出 `ApiError`；feature API 不重复实现错误处理。

## 5. SSE

- AI 问答与 sidecar 状态推送统一使用 POST SSE：原生 `fetch` 读取流，`eventsource-parser` 解析；原生 `EventSource` 因不支持 POST 而不使用。
- 事件类型固定为 `token`、`status`、`citation`、`interrupt`、`done`、`error`，调用方必须显式处理 `error` 和 `done`。
- 连接同样携带 `X-KnowRealm-Token`；组件卸载或用户停止时调用 `AbortController.abort()`，防止连接泄漏。
- `records.status`、`processing_jobs` 等状态最终以 sidecar 进程内事件经 SSE 推送；不引入 Realtime 或 WebSocket。阶段例外：plan 05 在 plan 04 接入 SSE 前，仅对 PENDING/RUNNING 文档任务使用条件轮询；终态立即停止。plan 04 完成后，轮询只作断线兜底。
- 状态事件的消费路径固定为：事件到达 → queryKey 工厂定位缓存 → `invalidateQueries` → Query 重取。
