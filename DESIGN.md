---
version: beta
name: KnowRealm-AI Desktop
description: 连续、克制、有纸面秩序感的个人学习桌面工作台
colors:
  ink: "#242424"
  ink-strong: "#171717"
  paper: "#FCFCFB"
  canvas: "#F6F6F4"
  surface-subtle: "#EEEEEB"
  surface-strong: "#E6E6E2"
  border-control: "#D8D8D4"
  text-muted: "#6B6B67"
  neutral-foreground: "#5C5C58"
  focus: "#70706B"
  success: "#4D9C78"
  success-foreground: "#286A4E"
  success-soft: "#E5F2EB"
  learning: "#4772D9"
  learning-foreground: "#254FAF"
  learning-soft: "#E8EEFC"
  warning: "#D77B16"
  warning-foreground: "#844500"
  warning-soft: "#F8EBD9"
  danger: "oklch(0.577 0.245 27.325)"
  dark-canvas: "#191918"
  dark-paper: "#20201F"
  dark-surface-subtle: "#292927"
  dark-surface-strong: "#32322F"
  dark-border-control: "#41413D"
  dark-muted: "#A7A7A1"
  dark-success-foreground: "#82C9A8"
  dark-success-soft: "#24372E"
  dark-learning-foreground: "#96B2F5"
  dark-learning-soft: "#26324D"
  dark-warning-foreground: "#F3B467"
  dark-warning-soft: "#3D3021"
  dark-neutral-foreground: "#C2C2BC"
typography:
  headline:
    fontFamily: "Noto Sans SC Variable, Geist Variable, sans-serif"
    fontSize: "26px"
    fontWeight: 650
    lineHeight: 1.28
    letterSpacing: "-0.02em"
  section:
    fontFamily: "Noto Sans SC Variable, Geist Variable, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Noto Sans SC Variable, Geist Variable, sans-serif"
    fontSize: "14px"
    fontWeight: 450
    lineHeight: 1.55
    letterSpacing: "-0.005em"
  body-dense:
    fontFamily: "Noto Sans SC Variable, Geist Variable, sans-serif"
    fontSize: "13px"
    fontWeight: 450
    lineHeight: 1.45
    letterSpacing: "0em"
  label:
    fontFamily: "Noto Sans SC Variable, Geist Variable, sans-serif"
    fontSize: "12px"
    fontWeight: 520
    lineHeight: 1.4
    letterSpacing: "0.01em"
rounded:
  panel: "0px"
  xs: "3px"
  sm: "5px"
  md: "8px"
  lg: "10px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  2xl: "32px"
  sidebar: "224px"
  topbar: "64px"
  content-gutter: "28px"
---

# Design System: KnowRealm-AI Desktop

## 1. Creative North Star

**连续工作面（Continuous Work Surface）**

KnowRealm 是长期驻留的桌面学习工具。页面应像一张持续展开、被认真排版过的工作台：侧栏、捕获栏和内容区是稳定色面；任务、学习链和资产通过标题、基线、留白与行节奏自然分组，不装进独立卡片。2026-09-07 基线修订：**今日页统计图表区升级为卡片面板**（主内容区灰底、图表卡白底，见 §4/§5），这是全站唯一的卡片化分区，其余区域仍执行零卡片 chrome。

ChatGPT Desktop 提供“界面后退、内容前进”的克制；腾讯 WorkBuddy 提供中文桌面生产力工具的紧凑字体、稳定坐标和低装饰控制。KnowRealm 吸收这种成熟度，但保留自己的学习链和知识状态语义。

### 必须呈现的性格

- 安静但不苍白：使用近白纸面与暖中性灰，不用刺眼纯白堆叠。
- 连续而非卡片化：一个页面是一张工作面，模块不是漂浮盒子。
- 精确但不机械：中文字体、行高、标点和数字对齐共同提供质感。
- AI 状态可信：处理、确认、生成和复习阶段清楚，但彩色只服务状态。

## 2. Material & Color

界面由三层连续色面构成：`canvas` 是应用底色，`paper` 是主工作面，`surface-subtle` 是选中、hover、表头和聚焦区域。常驻内容区禁止依靠阴影或闭合边框制造层级。

- `ink-strong`：页面标题、关键数字和主动作。
- `ink`：正文、导航和数据标题。
- `text-muted`：时间、来源、说明；不承担关键正文。
- `border-control`：只用于输入框、菜单、弹层和必要的行分隔，不用于卡片外框。
- 学习蓝、掌握绿、提醒橙只回答状态问题；单视区彩色面积不超过 8%。
- 小号语义文字使用 `*-foreground` + `*-soft`，普通文字对比度必须达到 4.5:1。

**禁止：** 大面积纯白卡片、玻璃、渐变、发光、重阴影、彩色图标底座和为“高级感”添加的噪点纹理。

## 3. Typography

中文主字体为项目内打包的 **Noto Sans SC Variable**，英文与数字回退至 Geist Variable。禁止把中文交给系统默认字体临时兜底。

- 页面标题：26px / 650，紧凑字距，用于当前工作上下文。
- 统计大数字：36px / 650，等宽数字，紧凑字距；单位与对比说明降低一级（12px / 520）。
- 分区标题：15px / 600；不通过更大的盒子或底色抢层级。
- 正文：14px / 450，行高 1.55，兼顾桌面密度与中文辨识。
- 密集信息：13px / 450；状态与元数据 12px / 520。
- 统计数字启用等宽数字；数字权重 620–650，单位与说明降低一级。
- 同一视区最多三个明显字号和三个字重。粗体只用于标题、当前状态和关键数字。

字体质感来自真实字族、克制字重和稳定基线，不使用无意义的全大写、宽字距或超粗中文。

## 4. Layout

- 左侧导航：224px；小于 1100px 压缩为 64px 图标栏。
- 顶部捕获栏：64px；作为工具轨而不是第二张导航卡。
- 主内容：28px 桌面外边距，最大宽度 1480px；模块间距 28–32px。
- 1440×900 首屏应完整显示今日标题、学习链、核心列表和统计摘要。
- 页面整体禁止横向滚动；表格在窄屏优先隐藏低优先级列。

今日页结构固定为：上下文标题 → 横向学习链焦点区 → 左侧行动流 / 右侧资产流 → 底部统计图表区。统计图表区是阅读路径的收束段：学习趋势主卡（含六格指标行）+ 一排洞察小图卡（学科能力 / 时间分布 / 专注度 / 进步趋势）。

## 5. Shape Language

内容容器默认执行 **Zero Card Chrome**；今日页统计图表区按 2026-09-07 基线修订采用**统计图表卡**：

- 默认（列表、表格、常规分区）：`border: 0`、`border-radius: 0`、`box-shadow: none`；分区通过留白、标题、非闭合基线或浅色面区分，不得补回闭合外框。
- 统计图表卡（仅今日页统计区）：`bg-card` 底 + `radius-lg`（10px）圆角 + 低对比描边（`border` 色 60% 透明度）；**禁止阴影**；卡内元素仍执行零卡片（无内嵌小卡、无内嵌圆角面板）。
- 主内容区底色为 `canvas`，图表卡以 `card` 色面浮出层次；暗色主题沿用同一关系。
- 表格与列表允许使用低对比行分隔或 hover 色面，但不把每行做成卡片。
- 静态信息行不得使用 hover 色面、指针光标或交互角色伪装成可点击项；只有存在真实动作或导航的行才呈现交互反馈。
- 按钮、输入框、菜单保留 5–10px 功能性圆角；短状态标签使用 3–5px，不默认胶囊化。
- 圆形只用于头像、通知点、进度节点和纯图标动作。

## 6. Components

### Application Shell

- 侧栏与主工作面使用相邻中性色面，不用边框把两者包成独立卡片。
- 当前导航使用浅色实面、较高字重和清楚图标；hover 只改变底色。
- 捕获栏的主录音按钮保持深墨色；其余动作使用 ghost 语法。
- 搜索与空间切换是输入/选择控件，可以使用边框和 8px 圆角。

### Buttons & Pointer

- 所有 `button`、链接、`[role="button"]`、可点击表格行与菜单项，在可用状态必须显示 `cursor: pointer`。
- disabled 控件使用 `cursor: not-allowed`，并保持标签可读。
- 主按钮为深墨底、纸白字；hover 只做 4–6% 明度变化，active 下移 1px。
- ghost 按钮无常驻边框；hover 使用 `surface-subtle`。
- `focus-visible` 使用 3px 半透明焦点环，不能用 hover 替代焦点。

### Workspace Sections

- 标题、说明与操作排列在同一基线；内容紧随其后。
- 常驻分区无外框、无圆角、无阴影；只有学习链焦点区可使用整块 `surface-subtle` 色面。
- 分区之间至少有 28px 空间，内部标题到内容保持 12–16px。

### Settings Surfaces

- 设置与偏好页面使用分类导航 + 配置工作面的连续布局，不把分类导航、配置分组或设置项包进卡片。
- 设置项禁止闭合描边、阴影和行分割线；层级只由留白、对齐、字重与选中态浅色面建立。输入框、按钮、菜单等真实控件仍保留功能性边框与 5–10px 圆角。
- 桌面宽度保持左侧分类导航；窄窗口改为顶部横向分类栏。分类切换不得造成页面横向溢出或丢失未保存输入。
- 本节限制只作用于设置类表单页面；数据表格及其他高密度列表仍按 Lists & Tables 规则使用必要的行分隔。

### Lists & Tables

- 行高 42–48px，主标题与元数据共用稳定文本基线。
- 可交互行的 hover 使用浅色整行背景，不改变尺寸、字重或列宽；静态行不使用 hover 反馈。
- 长标题单行截断并保留 `title`；关键总结允许两行。
- 数字右对齐并启用 tabular nums。

### Status

- 状态标签采用 3–5px 小圆角，不使用大胶囊。
- 色彩之外必须有文字；空间允许时加入 6px 状态点。
- “待确认”是学习链的最高行动优先级，但不使用警示大色块。

## 7. Motion

- 页面只允许一次 160–200ms 的轻微内容就位动画。
- hover/active 过渡为 120–160ms；禁止悬浮、缩放和弹簧效果。
- 完整支持 `prefers-reduced-motion`，关闭非必要动画。

## 8. Responsive & Accessibility

- 1440×900、1280×800、1099×720 为主页必测尺寸。
- 小于 1280px 时隐藏资产来源等低优先级列；小于 1100px 时压缩侧栏并将双栏改为单栏。
- 统计带六格指标在 1280px 宽度保持三列，达到 1400px 后展开为六列；洞察小图卡 1280px 两列、1400px 四列，更窄折单列。
- 纯图标按钮必须有可访问名称；键盘焦点可见；页面无整体横向溢出。
- 深色主题沿用相同连续色面与图表卡规则，不重新引入亮边框卡片。

## 9. Acceptance Rules

- 移除文字后，页面仍应由连续色面、稳定网格和一条学习链识别，而不是靠圆角卡片识别。
- 统计图表区之外，任何新增卡片外框、卡片圆角或卡片阴影都视为设计回退；统计图表卡自身禁止阴影。
- 任何可点击控件没有指针光标都视为交互缺陷。
- 中文若回退到系统默认字体，视为构建或字体装配缺陷。
- 构建通过不等于视觉通过；必须检查实际 Tauri/浏览器渲染、hover、focus、暗色和响应式。
