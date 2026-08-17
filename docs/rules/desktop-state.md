# 规范：桌面端状态管理（TanStack Query + Zustand）与通信层

> 适用范围：`stores/`、`services/http/`、`services/tauri/`、各 feature 的数据获取代码。

## 0. 版本基线（2026-08 核实）

| 依赖 | 基线 |
|---|---|
| @tanstack/react-query | **v5**（对象签名，位置参数已移除） |
| zustand | **v5**（5.0.x） |
| eventsource-parser | 最新（SSE 解析，替代已停更的 `@microsoft/fetch-event-source`） |

> 持久化缓存**不用** `@tanstack/react-query-persist-client`——localhost sidecar 毫秒级响应，内存缓存即可（见 §2.3 裁决）。

## 1. 状态分家（最重要的一张表）

写代码前先问：**这个数据谁拥有？**

| 数据 | 归属 | 例子 |
|---|---|---|
| sidecar 拥有、会变 | **TanStack Query** | 记录列表、课程、统计、AI 产出 |
| 纯浏览器/本机会话状态 | **Zustand** | 录音进行中的电平、播放器进度、弹窗开关 |
| 应该出现在 URL 里 | **Router searchParams** | 列表筛选、分页、tab |

> 无登录会话（本机单用户，决策 #55）——没有 token/会话状态可管。

```tsx
// ❌ 最常见错误：把服务端数据搬进 Zustand
const useRecordsStore = create((set) => ({
  records: [],
  fetchRecords: async () => set({ records: await api.getRecords() }),  // 双份事实源！
}));

// ✅ 服务端数据只经 useQuery，Zustand 只放真正的客户端状态
const { data: records } = useQuery({ queryKey: recordKeys.list(courseId), queryFn: ... });
const useRecorderStore = create<RecorderState>()(...);   // 电平、分片计数、录制状态
```

## 2. TanStack Query v5

### 2.1 写法（对象签名）+ queryKey 工厂

```tsx
// features/records/api/keys.ts —— 每个 feature 一份 key 工厂
export const recordKeys = {
  all: ["records"] as const,
  list: (courseId: string) => [...recordKeys.all, "list", { courseId }] as const,
  detail: (id: string) => [...recordKeys.all, "detail", id] as const,
};

// 使用
const { data, isPending, isError } = useQuery({
  queryKey: recordKeys.list(courseId),
  queryFn: () => recordApi.list(courseId),
  staleTime: 60_000,
});
```

- v5 术语：加载中用 `isPending`（`isLoading` 是 `isPending && isFetching` 的旧别名，新代码不用）。
- key 是**唯一事实**：同类数据不同参数（courseId、分页）必须体现在 key 里，否则互相覆盖缓存。

### 2.2 变更与失效

```tsx
const qc = useQueryClient();
const rename = useMutation({
  mutationFn: recordApi.rename,
  onSuccess: (_data, vars) => {
    qc.invalidateQueries({ queryKey: recordKeys.detail(vars.id) });   // 精确失效
    qc.invalidateQueries({ queryKey: recordKeys.all });               // 列表也刷
  },
});
```

- 改完数据**必须 invalidate** 对应 key；忘记失效 = 界面显示旧数据，这是最常见 bug 来源。
- 简单改名用乐观更新（`onMutate` + 回滚），长流程（生成总结）不用乐观、靠 SSE 事件驱动失效/轮询。

### 2.3 桌面端缓存策略（已裁决，2026-08）

**TanStack Query 内存缓存即可，无任何持久缓存**（技术栈 v4）——数据源是本机 sidecar（127.0.0.1 毫秒级），无离线场景；事实源只有 sidecar 背后的 knowrealm.db，前端不设第二份持久化业务数据（无 `cached_*` 表、无 `/api/sync`），重启后首轮查询直接命中 sidecar。

```tsx
// app/queryClient.ts
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,            // 桌面应用不是网页，别默认 0（每次挂载都打请求）
      retry: 2,
      refetchOnWindowFocus: false,  // 桌面窗口切换频繁，关掉
    },
  },
});
```

规则：
- **不使用 `persistQueryClient`**：按 queryKey 存序列化 blob，与"事实源在数据目录"的双份持久化必然漂移，且 blob 结构变更即整体作废。
- 浏览缓存随进程生灭；录音会话崩溃恢复不归 Query 管（那是 `recording_sessions` 事实，经 sidecar API 读取）。

## 3. Zustand v5

```tsx
// stores/recorder.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

type RecorderState = {
  isRecording: boolean;
  chunkCount: number;
  start: () => void;
  addChunk: () => void;
  stop: () => void;
};

export const useRecorderStore = create<RecorderState>()(
  persist(
    (set) => ({
      isRecording: false,
      chunkCount: 0,
      start: () => set({ isRecording: true, chunkCount: 0 }),
      addChunk: () => set((s) => ({ chunkCount: s.chunkCount + 1 })),
      stop: () => set({ isRecording: false }),
    }),
    {
      name: "recorder",
      partialize: (s) => ({ chunkCount: s.chunkCount }),   // 只持久化真正需要恢复的字段
    },
  ),
);
```

- **selector 最小订阅**：只取用到的字段，别整店订阅。

```tsx
// ❌ 组件在 chunkCount 变化时也会重渲（整店订阅）
const store = useRecorderStore();

// ✅ 只订阅需要的字段
const isRecording = useRecorderStore((s) => s.isRecording);

// ✅ 需要多个字段/派生对象时用 useShallow，防无限重渲
import { useShallow } from "zustand/react/shallow";
const { isRecording, chunkCount } = useRecorderStore(
  useShallow((s) => ({ recording: s.isRecording, chunks: s.chunkCount })),
);
```

- store 里只放 state 和 action，**不写副作用**（定时器、事件监听放组件/hook 里管理生命周期）。

## 4. 通信层（services/http）

### 4.1 统一 fetch 封装

所有后端请求走 `services/http/client.ts` 一个出口：统一错误类型；业务 API 按 feature 组织（`features/xxx/api/`）。

```ts
// services/http/client.ts —— 后端是 FastAPI sidecar（localhost）
export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${config.sidecarBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(resp.status, body.detail ?? "请求失败");
  }
  return resp.json() as Promise<T>;
}
```

- sidecar 端口由壳随机分配、经启动参数注入，UI 从 `config/` 读取（技术栈 v4 §十）；本机单用户**无认证头**。
- 这是 UI 与后端的**唯一通道**——不存在数据库直连层（红线 #35 v2.0）。

### 4.2 状态推送（sidecar 进程内事件 → SSE）

`records.status` / `processing_jobs` 状态变更由 sidecar 进程内事件经 **SSE** 推送（无 Realtime/WS——同进程组零网络，技术栈 v4）；UI 轮询 `refetchInterval` 仅作断连兜底。

SSE 事件的唯一消费方式：收到变更 → `invalidateQueries` 刷新对应 Query（配合 §2 的 queryKey 工厂），不在订阅回调里直接改本地 state：

```ts
// services/http/events.ts —— 状态事件订阅（经 §4.3 同一套 SSE 消费封装）
useEffect(() => {
  const sub = subscribeRecordEvents((recordId) =>
    queryClient.invalidateQueries({ queryKey: recordKeys.detail(recordId) }));
  return () => sub.unsubscribe();   // 组件卸载必退订，防止重复订阅
}, [queryClient]);
```

### 4.3 SSE（AI 问答流式 + 事件流解析）

SSE 消费用**原生 `fetch` POST 流式读取 + `eventsource-parser` 解析**（`@microsoft/fetch-event-source` 已停更，不再使用；原生 `EventSource` 不支持 POST，同样不用）。事件类型遵守功能需求基线 v2.1 §9.2 约定的六类：`token` / `status` / `citation` / `interrupt` / `done` / `error`：

```ts
// services/http/sse.ts —— 唯一的 SSE 消费封装（连接 + 解析），事件分发由调用方做
import { EventSourceParserStream } from "eventsource-parser";

export async function openSseStream(
  path: string, body: unknown,
  onEvent: (ev: { event: string; data: string }) => void,
  signal: AbortSignal,
) {
  const resp = await fetch(`${config.sidecarBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  const reader = resp.body!
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
    .getReader();
  while (true) {
    const { done, value: ev } = await reader.read();
    if (done || ev.event === "done") return;
    onEvent(ev);   // 调用方按六类事件分发：token（逐字渲染）/ status / citation
                   // （可跳转原声）/ interrupt（HITL 面板）/ error（不能无声断掉）
  }
}
// 组件卸载/用户停止时 AbortController.abort()，防止连接泄漏
```

## 5. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| 服务端数据存进 Zustand | TanStack Query（单一事实源） |
| queryKey 手写散落各处 | feature 的 `keys.ts` 工厂 |
| mutation 成功后不失效缓存 | `invalidateQueries` |
| `isLoading`（旧别名） | `isPending` |
| 整店订阅 `useStore()` | 字段 selector / `useShallow` |
| selector 里返回新建对象 | `useShallow` 包裹 |
| store 里写定时器/监听器 | 组件/hook 管理副作用 |
| 前端直连数据库 / 直写业务数据 | 一切经 sidecar API（`apiFetch` 唯一通道） |
| `@microsoft/fetch-event-source`（停更）/ 原生 `EventSource`（不支持 POST） | 原生 `fetch` + `eventsource-parser` |
| `persistQueryClient` / 本地持久缓存 | 内存缓存（localhost 毫秒级，事实源在数据目录） |
| SSE 订阅回调里直接改本地 state | 触发 `invalidateQueries`，让 Query 重取 |
| 只用轮询刷新状态 | SSE 事件为主，轮询仅兜底 |
| `staleTime` 默认 0（网页习惯） | 桌面端设合理 staleTime |
