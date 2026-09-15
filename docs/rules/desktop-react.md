---
paths:
  - "apps/desktop/src/**"
---

# 规范：桌面端 React + TypeScript + Router + i18n + 测试

> 适用范围：`apps/desktop/src/` 全部 TS/TSX。包管理 pnpm；依赖版本以 lockfile 为准。

## 1. 组件与目录

- 只写函数组件（禁 class）；文件名 = 组件名 PascalCase，一个文件一个导出组件；组件早返回优于深层嵌套，JSX 超 ~150 行拆子组件。
- 目录归属：`pages/` 只做布局与 Feature 组合；业务功能内聚 `features/xxx/`（组件/hooks/api/类型）；`components/ui/` 为 shadcn 生成件，`components/common/` 只放跨 Feature 公共组件——单 Feature 用的组件不进 common。
- 路径别名统一 `@/` → `src/`，禁多级 `../../` 相对导入。

## 2. Hooks 与类型

- Hooks 只在顶层调用；自定义 hook `use` 前缀，跨 Feature 复用放 `hooks/`；禁关 `react-hooks/exhaustive-deps`（确需省略写注释说明）。
- **API 数据类型一律从 `packages/api-types` 导入**（OpenAPI 自动生成），禁止手写重复接口定义。
- `strict` 零 `any`（逃逸用 `unknown` + 收窄）；状态机用字面量联合不用 `string`；优先判别联合 + 类型守卫，`!`/`as` 逐个注明理由。

## 3. 路由（TanStack Router，file-based）

- 路由树由生成器维护：新页面 = `pages/` 建路由文件，不手写 `createRoute` 编排。
- **URL 能表达的状态（筛选/分页/tab）放 searchParams（`validateSearch`），不放 Zustand**——刷新/分享链接才不丢。
- 导航一律 `useNavigate()` / `<Link>`，禁手拼 URL 字符串。

## 4. i18n

- 用户可见文案一律 `t("key")`（含 placeholder、toast、确认弹窗），禁硬编码中文；key 按 `feature.元素.用途` 分层。
- **zh / en 双语同步维护**，缺 key 不许合入。
- 术语约定：UI 文案以"学习会话 / 学习记录"泛称（代码实体仍为 Record），不写"上课/课堂"窄化措辞（学业场景除外）。

## 5. 测试（Vitest + Testing Library）

- 测用户行为不测实现细节：`getByRole` 优先，不依赖 class 名/内部 state。
- API mock 统一 MSW v2：handlers 集中管理 + `server.use()` 局部覆盖，不在组件测试手写 fetch stub。
