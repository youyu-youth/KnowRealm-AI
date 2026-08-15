# 规范：桌面端状态管理（TanStack Query + Zustand）与通信层

> 适用范围：`stores/`、`services/http/`、`services/tauri/`、各 feature 的数据获取代码。

## 0. 版本基线（2026-08 核实）

| 依赖 | 基线 |
|---|---|
| @tanstack/react-query | **v5**（对象签名，位置参数已移除） |
| zustand | **v5**（5.0.x） |
| @supabase/supabase-js | v2 |
| @microsoft/fetch-event-source | 最新 |

> 持久化缓存**不用** `@tanstack/react-query-persist-client`（见 §2.3 裁决）。

## 1. 状态分家（最重要的一张表）

写代码前先问：**这个数据谁拥有？**

| 数据 | 归属 | 例子 |
|---|---|---|
| 服务器拥有、会变 | **TanStack Query** | 记录列表、课程、统计、AI 产出 |
| 纯浏览器/本机会话状态 | **Zustand** | 录音进行中的电平、播放器进度、弹窗开关 |
| 应该出现在 URL 里 | **Router searchParams** | 列表筛选、分页、tab |
| 登录会话 | **supabase-js** | access token / 用户信息 |

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
- 简单改名用乐观更新（`onMutate` + 回滚），长流程（生成总结）不用乐观、靠轮询/Realtime。

### 2.3 桌面端缓存策略（已裁决，2026-08）

**持久化收敛到 SQLite `cached_*` 表 + `/api/sync` 游标增量拉取，TanStack Query 只做内存请求层**（对齐数据模型 §5/§7 的 L1 设计）；**不使用 `persistQueryClient`**——它按 queryKey 存序列化 blob，与 `cached_*` 行镜像双份持久化必然漂移，且 blob 不含 `synced_at`/游标元数据、不能 SQL 查询、结构变更即整体作废。

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

// 离线恢复：启动时从 cached_* 表预填缓存（代替 persistQueryClient）
async function hydrateFromCache(db: DesktopDb) {
  for (const c of await db.getCachedCourses()) {
    queryClient.setQueryData(courseKeys.list(), (old: Course[] | undefined) =>
      old ?? [fromCachedRow(c)]);   // 仅当内存无数据时预填，联网后静默刷新
  }
}
```

规则：
- 持久层事实 = `cached_*` 表（游标增量同步写入，可随时清空重建）；请求层 = Query 内存缓存。两层职责不重叠。
- 增量拉取走 `/api/sync`（`updated_at` 游标，存 SQLite `sync_cursor` 表），不靠 Query 重放全量请求。

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

所有后端请求走 `services/http/client.ts` 一个出口：注入 Bearer、统一错误类型；业务 API 按 feature 组织（`features/xxx/api/`）。

```ts
// services/http/client.ts —— 后端是 FastAPI（v3.2 定稿），目录注释里的 Spring Boot 是旧项目残留
export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = (await supabase.auth.getSession()).data.session?.access_token;
  const resp = await fetch(`${config.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token ?? ""}`,
      ...init?.headers,
    },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(resp.status, body.detail ?? "请求失败");
  }
  return resp.json() as Promise<T>;
}
```

- token 从 supabase-js 会话取（`supabase.auth.getSession()`），**不要自己存/刷新 token**。

### 4.2 supabase-js 的边界（只干三件事）

| supabase-js 负责 | 不负责 |
|---|---|
| Auth 会话（登录/登出/token） | ❌ 业务数据读写（一律走 FastAPI REST） |
| Storage 直传大文件（录音/课件，signed URL） | ❌ 在前端拼 SQL |
| Realtime 订阅（`records.status` / `processing_jobs` 变更推送） | ❌ 前端持 service role key（那是后端的） |

Realtime 订阅的唯一消费方式：收到变更 → `invalidateQueries` 刷新对应 Query（配合 §2 的 queryKey 工厂）；轮询 `refetchInterval` 仅为断连兜底。

```ts
supabase
  .channel(`record-${recordId}`)
  .on("postgres_changes", { event: "UPDATE", schema: "public", table: "records", filter: `id=eq.${recordId}` },
    () => queryClient.invalidateQueries({ queryKey: recordKeys.detail(recordId) }))
  .subscribe();
// 组件卸载时 supabase.removeChannel(channel)，防止重复订阅
```

### 4.3 SSE（AI 问答流式）

原生 `EventSource` 不能带 `Authorization` 头，**必须用 `@microsoft/fetch-event-source`**。事件类型遵守功能基线 §9.2 约定的六类：`token` / `status` / `citation` / `interrupt` / `done` / `error`：

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";

const ctrl = new AbortController();
await fetchEventSource(`${config.apiBaseUrl}/api/chat/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ question, courseId }),
  signal: ctrl.signal,
  onmessage(ev) {
    switch (ev.event) {
      case "token":     appendToken(ev.data); break;                  // 逐字渲染
      case "citation":  appendCitation(JSON.parse(ev.data)); break;   // 来源引用（可跳转原声）
      case "interrupt": showHitlPanel(JSON.parse(ev.data)); break;    // HITL 确认面板
      case "error":     showError(ev.data); break;
      case "done":      finish(); break;
    }
  },
  onerror(err) { /* 处理后 return 不重试，或 throw 让其重连 */ },
});
// 组件卸载/用户停止时 ctrl.abort()，防止连接泄漏
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
| 自己存/刷 token | `supabase.auth.getSession()` |
| 前端直接读写业务表 / 持 service key | 业务数据走 FastAPI |
| 原生 `EventSource` 消费 SSE | `fetchEventSource`（可带认证头） |
| `persistQueryClient` 持久化查询缓存 | `cached_*` 表 + sync 游标（单一持久事实） |
| Realtime 订阅后直接改本地 state | 触发 `invalidateQueries`，让 Query 重取 |
| 只用轮询刷新状态 | Realtime 为主，轮询仅兜底 |
| `staleTime` 默认 0（网页习惯） | 桌面端设合理 staleTime |
