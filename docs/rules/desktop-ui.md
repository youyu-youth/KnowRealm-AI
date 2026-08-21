# 规范：桌面端样式与组件体系（Tailwind CSS 4 + shadcn/ui + ECharts）

> 适用范围：`components/`、`charts/`、`styles/` 及所有写 JSX 样式的地方。

## 0. 版本基线（2026-08 核实）

| 依赖 | 基线 | 说明 |
|---|---|---|
| Tailwind CSS | **4.x** | 2025-01 GA，配置方式改为 **CSS-first**（`@theme`），不再用 `tailwind.config.js` |
| shadcn/ui | CLI **v4**（2026-03 起，`npx shadcn@latest`） | 源码进仓库（`components/ui/`，`components.json` 登记）；v4 同时支持 Radix 与 Base UI 双原语——底座约定见 §2 |
| lucide-react | 最新 | 图标唯一来源 |
| ECharts | **6.x**（2025-07 发布） | 从 5 升 6 注意官方 upgrade guide |

## 1. Tailwind CSS 4（CSS-first 配置）

设计令牌全部定义在 `styles/tokens.css` 的 `@theme` 块里，**不存在 `tailwind.config.js`**：

```css
/* styles/tokens.css */
@import "tailwindcss";

@custom-variant dark (&:where(.dark, .dark *));   /* 深色模式用 class 策略 */

@theme {
  --color-primary: oklch(0.55 0.15 250);
  --color-primary-hover: oklch(0.48 0.15 250);
  --radius-card: 0.75rem;
}
```

```tsx
// ✅ 令牌生成工具类，直接可用
<button className="bg-primary rounded-card hover:bg-primary-hover" />

// ❌ 魔法值（散落的 hex/任意间距）——换主题/调设计时全项目找不着
<button className="bg-[#3b82f6] rounded-[9px]" />
```

规则：
- 新颜色/字号/间距先加进 `@theme`，再用类名；**禁止魔法值**（`bg-[#...]`、`mt-[13px]`）。
- 深色模式一律 `dark:` 变量切换（`styles/theme.css` 定义两套语义变量），不写死深色 hex。
- 类名顺序交给 `prettier-plugin-tailwindcss` 自动排序，不手工纠结。
- 同一串类名复制粘贴超过 2 处 → 抽组件或 `cn() + cva` 变体，不复制。

```tsx
// cn() 合并类（shadcn 标准）；cva 管变体
import { cn } from "@/lib/utils";
import { cva } from "class-variance-authority";

const statusBadge = cva("inline-flex rounded-full px-2 py-0.5 text-xs", {
  variants: {
    status: {
      DONE: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      FAILED: "bg-red-500/15 text-red-600 dark:text-red-400",
      TRANSCRIBING: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    },
  },
});

<StatusBadge className={cn(statusBadge({ status }), className)} />
```

## 2. shadcn/ui

- 不重复造轮子，优先使用 shadcn ui  组件库，并符合设计规范

- 组件通过 CLI 添加：`npx shadcn@latest add button dialog table`，产物落在 `components/ui/`。
- **原语底座统一 Base UI**：shadcn CLI v4 起同时提供 Radix 与 Base UI 两套原语，本项目统一选 **Base UI** 底座（技术栈 v4.2 D2 定稿），**禁止混搭**（两套原语的行为、焦点管理与包体积会叠加，且修复方式互不通用）。
- **不手改 `components/ui/` 里的生成代码**（下次 add/diff 会覆盖）——定制在外面包装：

```tsx
// components/common/PageHeader.tsx —— ✅ 包装层传 className/props 定制
import { Button } from "@/components/ui/button";

export function PageHeader({ title, action }: PageHeaderProps) {
  return (
    <header className="flex items-center justify-between">
      <h1 className="text-lg font-semibold">{title}</h1>
      {action && <Button variant="outline" size="sm">{action}</Button>}
    </header>
  );
}
```

- 业务组件优先组合 shadcn/ui（Button/Dialog/Table/Sheet…）+ Base UI 行为，**不从零手写**交互控件。
- 图标只用 `lucide-react`，保持整套图标线性风格统一。

## 3. ECharts（`charts/` 公共图表层）

所有图表经 `charts/` 基础组件使用，页面不直接 `import "echarts"`：

```tsx
// charts/BaseChart.tsx —— 按需引入 + 统一生命周期
import * as echarts from "echarts/core";
import { LineChart, TreeChart } from "echarts/charts";
import { TooltipComponent, GridComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([LineChart, TreeChart, TooltipComponent, GridComponent, CanvasRenderer]);

export function BaseChart({ option }: { option: echarts.ComposeOption<...> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const chart = echarts.init(ref.current!);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    chart.setOption(option);
    return () => { window.removeEventListener("resize", onResize); chart.dispose(); };  // 防泄漏
  }, [option]);
  return <div ref={ref} className="h-72 w-full" />;
}

// pages 里使用（Knowledge GPS = TreeChart，遗忘曲线 = LineChart）
<BaseChart option={knowledgeGpsOption(masteryTree)} />
```

- **按需注册**（`echarts/core`），不整包 `import * as echarts from "echarts"`（体积近乎减半）。
- 图表颜色/字体读全局令牌，保证换主题时图表跟随。
- 每个图都必须处理 `resize` 与 `dispose`，漏掉 = 窗口缩放错位、内存泄漏。

## 4. Markdown 渲染（AI 输出 / 复习资料）

AI 对话答案、总结、复习资料都是 Markdown，统一经 `components/common/` 的渲染组件输出（`react-markdown`），页面不直接散用：

- **代码块必须高亮**（功能需求基线 v2.2：程序员场景 AI 输出默认含代码块）——统一用 **shiki**（技术栈 v4.2 定稿），主题跟随亮/暗令牌。
- **树形大纲思维导图**（复习资料的 Markdown 大纲，功能需求基线 v2.2 M4）：按标题层级解析渲染为可折叠树组件，不做图形化导图导出。
- AI 产出的 Markdown 属不可信输入：经 `rehype-sanitize` 白名单过滤，禁止 `dangerouslySetInnerHTML` 直染。

## 5. 资源与样式文件归属

| 内容 | 位置 |
|---|---|
| 设计令牌（颜色/圆角/间距） | `styles/tokens.css`（`@theme`） |
| 主题切换（亮/暗语义变量） | `styles/theme.css` |
| 全局 reset / 基础样式 | `styles/globals.css` |
| 动画 keyframes | `styles/animations.css` |
| 图片/插画/字体 | `assets/`（大文件放 `public/`） |

- 组件样式就近写在 className（Tailwind 之道），**不新建散装 `.css` 文件**；确需复杂选择器时集中到上述四个样式文件里。
- **偏好单一本地配置**（功能需求基线 v2.2 M1，决策 #51）：主题/字号/语言/时区/关窗行为/开机自启/速记快捷键/窗口记忆等全部存数据目录 `config/settings.json`（单一事实源，经 sidecar API 读写）——深色模式切换 = 改 `settings.theme` + 挂/摘 `<html>` 的 `.dark` class，不落第三处状态。

## 6. 可访问性（a11y）

- **交互组件一律用 shadcn/Base UI 原生**（Dialog/Popover/Select/Command 等自带焦点管理、键盘导航与 aria 属性）——这是"不从零手写交互控件"（§2）的另一半理由。
- **禁止全局移除 focus ring**（如 `outline-none` 不配替代样式）；需要定制时改用 `focus-visible:` 令牌样式，键盘用户要能看见焦点在哪。

```tsx
// ❌ 纯图标按钮没有可访问名称（屏幕阅读器读到"按钮"）
<Button variant="ghost" size="icon"><Trash2 /></Button>

// ✅ 带 aria-label
<Button variant="ghost" size="icon" aria-label={t("record.delete")}>
  <Trash2 />
</Button>
```

- 纯图标按钮必须 `aria-label`（走 i18n）；图标是装饰性文字补充时加 `aria-hidden`。
- 命令面板（Ctrl+K）、弹窗、下拉支持键盘：Esc 关闭、方向键移动、Enter 确认——用 Base UI 原生即自动获得，别用 `div` + `onClick` 手搓。
- 测试侧配合 `getByRole` 查询（desktop-react.md §6），角色查不到 = 可访问性缺口信号。

## 7. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| `tailwind.config.js` / JS 配置 | `@theme`（CSS-first） |
| 魔法值 `bg-[#xxx]` / `mt-[13px]` | 先加令牌再用工具类 |
| 手改 `components/ui/` 生成代码 | 外层包装组件定制 |
| 从零手写下拉/弹窗/表格 | shadcn/ui + Base UI |
| 混用多套图标库 | 只用 lucide-react |
| 整包 import echarts | `echarts/core` 按需注册 |
| 图表漏 dispose/resize | `charts/BaseChart` 统一封装 |
| 页面里直接操作 echarts 实例 | 经 `charts/` 基础组件 |
| 散装业务 `.css` 文件 | Tailwind 就近 + 四个全局样式文件 |
| 复制粘贴同串类名 3+ 次 | 抽组件 / `cn()+cva` |
| `div` + `onClick` 手搓交互控件 | shadcn/Base UI 原生（键盘 + aria 自带） |
| 移除 focus ring / 纯图标按钮无 `aria-label` | `focus-visible:` 定制 + `aria-label` |
| Radix 与 Base UI 原语混搭 | 全项目统一 Base UI 底座（CLI v4 起可选） |
