# 规范：桌面端 React + TypeScript + Router + i18n + 测试

> 适用范围：`apps/desktop/src/` 全部 TS/TSX 代码。包管理用 **pnpm（10 或 11，锁 12 以下——12 尚为 RC）**。

## 0. 版本基线（2026-08 核实）

| 依赖 | 基线 | 说明 |
|---|---|---|
| React | **19.x**（当前 19.2.x） | 已定稿（2026-08 裁决）：React 18 已停止主动开发（仅安全补丁），19.2 稳定近两年、生态全兼容；v3.2 基线已同步 |
| TypeScript | **6.0.x**（strict） | 7.0（Go 原生重写）已发布但属编译器架构更换，待生态工具链验证后再评估 |
| Vite | **8.x** | Rolldown 内核（2026-03 起），8.2 patch 线稳定；配套 Vitest ≥4.1 |
| TanStack Router | v1 | 与目录结构配套用 **code-based routing**（路由集中在 `app/router.tsx`，页面放 `pages/`） |
| i18next + react-i18next | 最新稳定 | — |
| Vitest + Testing Library | **≥4.1** | 4.1 起支持 Vite 8（v3 仅支持到 Vite 7） |

## 1. 组件规范

- **只写函数组件**，禁止新增 class 组件。
- 文件名 = 组件名，PascalCase：`RecordCard.tsx` 导出 `RecordCard`。一个文件一个导出组件。
- 目录归属（自上而下）：
  - `pages/`：路由级视图，只做布局与 Feature 组合；
  - `features/xxx/`：业务功能（组件、hooks、api 调用、类型内聚在一起）；
  - `components/ui/`：shadcn/ui 生成的基础组件；`components/common/`：跨 Feature 公共组件；
  - 只被一个 Feature 用的组件**不进** `components/common/`，放 feature 目录内。

```tsx
// ✅ props 类型显式定义，children 用官方类型
import type { ReactNode } from "react";

type RecordCardProps = {
  record: RecordSummary;        // 类型来自 packages/api-types（见 §3）
  onOpen?: (id: string) => void;
  children?: ReactNode;
};

export function RecordCard({ record, onOpen, children }: RecordCardProps) {
  return <article onClick={() => onOpen?.(record.id)}>{record.title}{children}</article>;
}
```

规则：**组件早返回**优于深层嵌套；JSX 超过 ~150 行考虑拆子组件。

- **路径别名统一 `@/` → `src/`**（`vite.config.ts` 的 `resolve.alias` + `tsconfig.json` 的 `paths` 同步配置），跨目录导入一律用别名：

```tsx
// ❌ 多级相对路径（重构移动文件即断）
import { cn } from "../../../lib/utils";

// ✅ 别名导入
import { cn } from "@/lib/utils";
import { RecordCard } from "@/features/records/components/RecordCard";
```

## 2. Hooks 规范

- 只在组件/hook 顶层调用，不在条件、循环、回调里调用（官方铁律，`eslint-plugin-react-hooks` 强制）。
- 自定义 hook 必须 `use` 前缀。跨 Feature 复用的放 `hooks/`，单 Feature 用的放 feature 目录内。
- 依赖数组交给 ESLint 检查，**禁止关闭 `react-hooks/exhaustive-deps`**，确实无需依赖时写注释说明原因。

```tsx
// ✅ 自定义 hook：封装"录音状态轮询"这类可复用逻辑
function useRecordStatus(recordId: string) {
  return useQuery({
    queryKey: recordKeys.detail(recordId),
    queryFn: () => recordApi.get(recordId),
    refetchInterval: (q) => (q.state.data?.status === "DONE" ? false : 3000),
  });
}
```

- **状态刷新以 Supabase Realtime 为主、轮询为兜底**（功能基线 §4.3.4）：Realtime 订阅 `records.status` / `processing_jobs` 变更后触发 `invalidateQueries`；`refetchInterval` 只作为 Realtime 断连时的降级手段，不要当作唯一刷新机制。

## 3. TypeScript 规范

- `tsconfig` 保持 `"strict": true`；新增代码零 `any`（确需逃逸用 `unknown` + 收窄）。
- **API 数据类型一律从 `packages/api-types` 导入**（FastAPI OpenAPI → openapi-typescript 自动生成），禁止在 `types/` 手写一份重复的接口定义——两份定义必然漂移。
- 状态机用**字面量联合类型**，不用 `string`：

```ts
// ❌ status: string —— 什么都能塞进去
// ✅ 状态机字面量联合
type RecordStatus =
  | "CREATED" | "UPLOADING" | "TRANSCRIBING"
  | "SUMMARIZING" | "REVIEWING" | "DONE" | "FAILED";

// ✅ 判别联合 + 类型守卫，代替 as 断言
type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

// ❌ const r = resp as RecordSummary
// ✅ if (result.ok) { ... result.data 自动收窄 }
```

- `!` 非空断言、`as` 断言逐个注明理由；优先用可选链与判别联合解决。

## 4. 路由（TanStack Router，code-based）

路由树集中在 `app/router.tsx` 定义，页面组件在 `pages/`，按 feature 懒加载：

```tsx
// app/router.tsx
import { createRootRoute, createRoute, createRouter, lazyRouteComponent } from "@tanstack/react-router";

const rootRoute = createRootRoute();

const recordsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/records",
  component: lazyRouteComponent(() => import("../pages/RecordsPage")),  // 路由级代码分割
  validateSearch: (search: Record<string, unknown>): { courseId?: string; page?: number } => ({
    courseId: typeof search.courseId === "string" ? search.courseId : undefined,
    page: Number(search.page ?? 1),
  }),
});

export const router = createRouter({ routeTree: rootRoute.addChildren([recordsRoute /* ... */]) });

// main.tsx 注册类型，让 useNavigate/useSearch 全局类型安全
declare module "@tanstack/react-router" {
  interface Register { router: typeof router }
}
```

规则：
- **URL 能表达的状态（筛选、分页、tab）放 searchParams**，不放 Zustand——刷新/分享链接才不丢。
- 导航一律 `useNavigate()` / `<Link>`，禁止手拼 URL 字符串。
- 新页面：`pages/` 建文件 + `router.tsx` 注册，两步缺一不可。

## 5. i18n（界面文案）

- 用户可见文案**一律 `t("key")`**，禁止硬编码中文字符串（含 placeholder、toast、确认弹窗）。
- key 按 `feature.元素.用途` 分层：`record.list.emptyTitle`。
- **术语约定（功能基线 v1.4）**：UI 文案以"**学习会话 / 学习记录**"泛称（覆盖课堂、技术分享、培训、自学），代码与数据实体仍为 Record——不写"上课/课堂"这种窄化措辞（学业场景文案除外）。

```tsx
const { t } = useTranslation();
<p>{t("record.list.emptyTitle")}</p>
```

- 语言文件放 `i18n/locales/{zh,en}.json`；新文案 zh/en 同步补齐，缺 key 不许合入。

## 6. 测试（Vitest + Testing Library）

- 测**用户行为**不测实现细节：通过可访问角色查询元素（`getByRole` 优先），不依赖 class 名/内部 state。
- 关键业务逻辑（状态机流转、录音分片索引、缓存工具）必须有单测；纯展示组件不强制。
- **API mock 统一 MSW v2**（对齐 bulletproof-react 约定）：handlers 集中在 `mocks/handlers.ts`、测试实例由 `mocks/server.ts` 导出（Vitest setupFiles 注册）；单测用 `server.use(...)` 局部覆盖特定路由，不在组件测试里手写 fetch stub。

```tsx
test("显示记录标题", async () => {
  server.use(http.get("/api/records/:id", () => HttpResponse.json(mockRecord)));
  render(<RecordCard record={mockRecord} />);
  expect(screen.getByRole("heading", { name: "操作系统第一课" })).toBeInTheDocument();
});
```

## 7. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| class 组件 | 函数组件 + hooks |
| 手写 API 类型（与 api-types 重复） | 从 `packages/api-types` 导入 |
| `status: string` 之类的宽类型 | 字面量联合 + 判别联合 |
| `any` / 随手 `as` / `!` | `unknown` + 类型收窄 |
| 硬编码中文文案 | `t("key")` |
| 手拼 URL 导航 | `useNavigate` / `<Link>` |
| 筛选/分页状态放 Zustand | searchParams（`validateSearch`） |
| 关闭 exhaustive-deps 或漏依赖 | 完整依赖数组 |
| 多级 `../../` 相对导入 | `@/` 别名 |
| 页面组件里堆业务 | 拆到 `features/` 组合 |
