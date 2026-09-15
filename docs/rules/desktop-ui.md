---
paths:
  - "apps/desktop/src/**"
---

# 规范：桌面端样式与组件体系（Tailwind 4 + shadcn/ui + ECharts）

> 适用范围：`components/`、`charts/`、`styles/` 及所有写 JSX 样式的地方。Tailwind 4 CSS-first（`@theme`，无 tailwind.config.js）。

## 1. Tailwind 与令牌

- 设计令牌只定义在 `styles/tokens.css` 的 `@theme`；新颜色/字号/间距先加令牌再用类名，**禁魔法值**（`bg-[#...]`、`mt-[13px]`）。
- 深色模式一律 `dark:` class 策略（`styles/theme.css` 两套语义变量），不写死深色 hex；类名顺序交 prettier-plugin-tailwindcss；同一串类名复制超 2 处抽组件或 `cn()` + `cva`。
- ⚠️ 未定义的颜色 token 会让工具类**静默无色**——用前先确认 tokens.css / theme.css 已定义。

## 2. shadcn/ui 与图标

- 组件经 CLI 添加（产物落 `components/ui/`），**不手改生成代码**（add/diff 会覆盖），定制在外面包装。
- **原语底座统一 Base UI，禁与 Radix 混搭**（行为/焦点管理/修复方式不通用）；交互控件不从零手写（shadcn/Base UI 自带焦点管理、键盘导航、aria）；图标只用 lucide-react。

## 3. ECharts

- 一律经 `charts/BaseChart`：`echarts/core` 按需注册（禁整包 import）；必须处理 resize 与 dispose（漏 = 缩放错位 + 内存泄漏）；图表颜色/字体读全局令牌。

## 4. Markdown 渲染

- Chat 消息用 Streamdown（`features/chat/ChatMarkdown.tsx`，含 code/math/cjk 扩展）；总结、复习资料等其余场景统一经 `components/common/` 的 react-markdown + shiki 渲染组件。
- AI 产出 Markdown 属不可信输入：经 sanitize 白名单过滤，禁 `dangerouslySetInnerHTML` 直染。

## 5. 偏好与主题（settings.json 单一事实源）

- 主题/字号/时区/关窗行为/自启/快捷键/上次路由/默认习题数量存数据目录 `config/settings.json`（sidecar API 读写，缺键=默认、未知键保留），不落第三处状态。
- 深色切换 = 改 `settings.theme` + 挂/摘 `<html>` 的 `.dark`/`.light` class；SYSTEM 由应用器解析 `prefers-color-scheme` 后同样落到 class，**不双摘**（双摘会让系统深色下全部 `dark:` 工具类失效）；JS 应用前的首帧由 theme.css 媒体查询兜底。
- 唯一豁免：窗口几何由官方 tauri-plugin-window-state 存自身配置。偏好消费优先 Tauri 官方件（快捷键=global-shortcut JS API、关窗分流=onCloseRequested、自启=autostart 插件），Rust 侧不新增偏好命令。

## 6. 可访问性

- 纯图标按钮必须 `aria-label`（走 i18n）；图标为装饰性文字补充时加 `aria-hidden`；禁全局移除 focus ring（用 `focus-visible:` 令牌样式替代）。
- 键盘交互（Esc/方向键/Enter）用原语自带，别 `div` + `onClick` 手搓；测试 `getByRole` 查不到 = 可访问性缺口信号。
