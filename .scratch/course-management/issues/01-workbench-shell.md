# 01 — 工作台骨架与真实空态

**What to build:** 让学习者启动 KnowRealm 后进入一个稳定、可键盘操作的 Continuous Work Surface；“今日”和“知识空间”能够真实导航，尚未实现的工作区与捕获动作明确显示为未接入且不会产生假行为。

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] 应用具备稳定的左侧导航、顶部捕获栏、内容路由出口、当前导航状态以及全局加载、错误和未找到边界。
- [x] “今日”和“知识空间”可通过类型安全路由进入；未知地址提供返回路径。
- [x] 今日页只显示真实空态与后续内容宿主，不包含模拟待办、统计或 AI 状态。
- [x] 知识空间页显示真实空态与新建课程入口位置，但本票不伪造保存成功或课程数据。
- [x] 收件箱、AI 对话、资产库、学习画像及捕获动作使用可访问的不可用语义并显示“未接入”，不能导航到静态假页面。
- [x] 所有用户可见文案来自中文 i18n 资源；纯图标控件具有可访问名称，键盘焦点始终可见。
- [x] 布局遵循既有设计合同：224px 侧栏、64px 捕获栏、28px 内容边距和 Zero Card Chrome；小于 1100px 时侧栏压缩为 64px。
- [x] 亮色、暗色、1440×900、1280×800、1099×720 均无整体横向溢出；静态信息没有 hover 或 pointer 伪交互。
- [x] 桌面构建、lint、行为测试和一次真实渲染检查通过；构建结果与渲染证据分别记录。

## Comments

- 2026-08-17：Ticket 01 实现完成。`pnpm run test`（2/2）、`pnpm run lint`、`pnpm run format:check`、`pnpm run build` 与 staged diff check 通过。
- 真实渲染证据：1440×900 / 1280×800 / 1099×720 / 暗色 1280×800；无整体横向溢出，侧栏为 224 / 224 / 64 / 224px，标题/正文字重为 650/450，Noto Sans SC 生效。
- 交互证据：真实点击 `/` → `/spaces`；Tab 焦点依次到“今日”“知识空间”并跳过 disabled；disabled 计算样式为 `cursor: not-allowed`，hover 前后背景不变。
- Impeccable 最终 disposition `ship`；双轴代码审查 Standards PASS、Spec PASS。截图右侧的粉色悬浮控件来自 browser-use harness，不属于应用。
