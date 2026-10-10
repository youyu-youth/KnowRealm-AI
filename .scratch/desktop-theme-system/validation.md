# 独立明暗主题系统实施与验收

日期：2026-10-10。分支：`feat/extend-dev-08`。固定审查基线：`ee06877c8210388829d399dad5f24ce212cf544b`。

功能代码已实现并提交；工单仍有未完成的真实验收，不能宣称 T01–T16 全部闭合。用户已批准 [权威文档提案](authority-proposal.md)，DESIGN.md / GLOSSARY.md 已同步。

## 实现边界

- 复用偏好 API、原子文件替换及五个配置写入口的提交锁。独立 `light_theme_id` / `dark_theme_id` 使用生成契约类型；缺键默认、默认删键、单组损坏回退、非法输入拒绝及未知键保留，无数据库迁移。
- 主题登记及模式解析集中在 `appearance.ts`；四套配色留在样式层，默认主题保留原有实际取值。页面和课程封面消费语义变量，新增主题不需要逐页面增加分支。
- 两组选择复用设置行和 Base UI 单选；即改即存，当前组即时应用，另一组仅保存；语言、字号、向导、路由记忆及习题数量沿用共享写入口，保存中阻止冲突。
- Query 保留已确认事实。失败回退并直接 GET 对账；PUT 成功及对账完成后再次取消期间启动的旧查询，阻止迟到 GET 覆盖确认结果；派生缓存不保存候选值。
- 缓存绑定 IPC 确认的当前数据目录。主入口等待权威偏好或规定的失败降级之后才挂载工作区；SYSTEM 订阅系统事件，手动模式不注册该监听。
- 根元素更新颜色变量及外观事件；图表 wrapper 重新计算配色，BaseChart 合并换色而保留实例和交互。移除 TodayStatsBand 因主题变化的重挂载。换色首帧暂时关闭控件 CSS 过渡，双 RAF 后恢复原反馈，不新增业务动画。
- 本期不接入 Agent：仅作用于当前本机工作区，确定性外观解析由 Desktop 完成；后端只存储和校验，不新增外观 Tool、LLM、Rust 主题命令、依赖或后台任务。

## 自动化证据

| 范围 | 结果 |
| --- | --- |
| 后端现有偏好和全量归档测试 | 78 passed；真实配置读回、并行部分更新、非法请求、全量导出导入恢复两组选择 |
| 后端 pyright、触及 Ruff lint / format | 通过，pyright 0 errors / warnings |
| OpenAPI 与 API 类型漂移检查 | 通过 |
| 最终相关前端设置、缓存、保存交错、统计原测试及主题状态测试 | 5 文件、50 passed，65.79s；见 `native/verified-final-tests.log` |
| 最终 TS 检查、生产构建、触及 ESLint / Prettier | 通过；构建 40.83s，既有大 chunk 提示保留；见 `native/final-build.log` |
| 前端全量初轮 | 76 文件，697 passed / 7 failed（704 项），222.27s；见 `full-tests.log` |
| 最终前端全量 | 78 文件，700 passed / 7 failed（707 项），293.03s；失败仍为基线复现的相同 7 项，见 `final-full-tests.log` |
| 全仓前端 lint | 未通过：未修改的 PlanDraftEditor.tsx:55 与 LearningPlanTab.tsx:760 各一条 react-refresh/only-export-components 警告，max-warnings=0 拦截 |

初轮全量的 7 个失败已在上述原始基线的隔离 checkout 复现：4 文件、44 passed / 7 failed（51 项），137.81s，见 `baseline-tests.log`。涉及 inbox.test.tsx（2）、LearningPlanTab.test.tsx（3）、RecordDetail.test.tsx（1）、CommandPalette.test.tsx（1）。对照复用同一安装依赖，并复制基线依赖但被忽略的未修改 `src/lib/utils.ts`；不是洁净依赖环境，也不是基线全量通过。未扩展无关修复范围。

## 真实 Tauri / WebView2

测试使用独立 identifier `ai.knowrealm.theme-validation` 和 `native/data`，IPC 已确认目录。实际 Windows 系统缩放 125%，WebView2 DPR 1.25；使用生产构建，由本地 preview 加载，无 HMR 干扰。Windows 应用外观的测试修改已恢复为原值 `AppsUseLightTheme=1`。

| 已执行场景 | 证据及范围 |
| --- | --- |
| 四主题的今日、知识空间、资料库、聊天、设置及壳层 | 20 张截图与 `native/matrix.json`；独立空测试数据；Today 中产品既有示意内容保留示意标识，不能当作真实学习数据 |
| 当前组立即应用、另一组仅保存及手动模式恢复 | 真实设置控件操作；两组预览使用固定 palette，选中语义独立 |
| SYSTEM 跟随 Windows 应用外观 | 修改真实系统外观设置并广播系统设置事件，明亮→墨蓝→青灰；`native/windows-dark-event.json`、`windows-light-event.json`；两种手动模式分别不随系统变化，另有 `windows-manual-*.json` |
| 三档字号 × 四主题，真实窄窗 | 设置/今日 24 截图，CSS viewport 886×712、DPR 1.25，根字号 15/16/18px；无 body 横向溢出；见 `native/narrow/matrix.json`；已目检大字号青灰设置、墨蓝今日 |
| 键盘和减少动效 | 原生 WebView2 中方向键选择主题并保留焦点；减少动效通过 CDP 注入媒体偏好（不冒充 Windows 辅助设置切换）；见 `native/narrow/keyboard-reduced-motion.png` |
| 图表与统计状态 | 五个真实 ECharts SVG 节点在同模式及跨模式换色后保持实例，SVG 更新、统计折叠保持；见 `native/chart-preservation.json`、`charts-LIGHT_SAGE.png`、`charts-DARK_INK.png` |
| 图表换色性能 | 根状态与事件按生产应用流程注入，六次切换 × 五图表 SVG 更新均低于 120ms，最终最大 62.9ms，见 `native/chart-timing-final.json`；这是本地 SVG 更新测量，不包含 HTTP 或物理显示器扫描。最终复测窗口已还原且未最小化；焦点、viewport 与 DPR 随结果记录。修复前 `chart-timing*.json` 保留失败诊断，不能当最终成绩；日常过渡最终复测均已恢复 |
| 表单与浮层保持 | 速记 Dialog 的输入、节点、焦点与选择区间在同模式换主题后保留；见 `native/draft-dialog-sage.png`；未覆盖持续聊天或活动录音 |
| 六类启动缓存场景 | 手动明亮缺缓存、暗黑有效、明亮损坏、暗黑错目录、SYSTEM 有效及失效主题；工作区首次可见 RAF 均为目标主题，实际 screencast 截图各 6–9 帧；见 `native/startup/matrix.json`。这是 WebView2 页面重载，不是六次 OS 进程冷启动 |
| 实际进程重启 | 使用既有 Tauri restart：新 PID 与 IPC 测试目录已确认，权威 DARK_INK 覆盖有效但陈旧的 LIGHT 缓存；见 `native/process-restart/restored.json`。桌面捕获的 59 帧记录到宿主白底阶段，未证明工作区首次显示全过程无错帧，不能代勾冷启动矩阵 |

默认变量逐项与存储阶段提交中的真实默认值对照相同，课程封面默认两组 palette 原值保留。尚未完成改动前后真实界面的完整像素及各控件状态对照；菜单、Tooltip、Toast、完整对比度及课程关系图交互保留待验收。

## Standards

独立审查未发现实质规范违规或需要整改的代码气味。契约、登记、存储、应用及缓存分责，复用设置组件和平台入口，无通用配置框架。仅静态审查；视觉和性能以主线程证据为准。

## Spec

独立审查发现 1 项 P2：保存期间启动的旧 GET 可迟到覆盖成功 PUT 或失败对账结果。`b52bfa1` 在两条确认边界再次取消查询；参数化测试分别让旧 GET 在 PUT 等待期间、直接对账 GET 等待期间启动，确认完成后才释放。审查复核已关闭该问题，未发现其他确定逻辑缺陷或范围扩大。未验证的真实场景仍是验收缺口。

Standards 0 项；Spec 1 项 P2 已修复，未关闭代码问题 0 项。双轴静态审查不代表所有真实验收完成。

## 尚未完成与环境保留

- 真实 Windows 200%（不是改 DPR / viewport）、全部冷启动矩阵、持续聊天与活动录音换主题、任务订阅不中断，以及全量导入和目录迁移之后的真实客户端缓存校正。
- 全应用菜单/Tooltip/Toast、hover/active/disabled/loading/error、量化对比度及改动前默认界面完整视觉对照。已有局部证据不替代上述完整组合。
- 自动审批拒绝停止测试 preview 服务的命令，仅给出 `blocked by policy`，因此没有切换到隔离基线的 preview 做像素对照。此前 pytest 临时目录清理也被同样拒绝，未绕过；临时目录、隔离 checkout、运行日志及截图保留，未提交业务数据或配置凭据。
- 原有未跟踪 `spec.md` 保持原状，未代提交。未运行全量后端测试，不修复历史前端测试及 lint 问题。

此状态为待人工补齐验收；原生宿主白底捕获问题及剩余工单项明确保留，不将部分实现或检查登记为整票完成。
