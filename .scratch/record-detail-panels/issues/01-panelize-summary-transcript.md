# 01 — RecordDetailPage 拆域为 Summary / Transcript 深面板

**What to build:** 在严格保持现有用户界面、API 调用、请求启用条件、缓存失效、错误处理与 URL 行为不变的前提下，把 Record 详情中完整的 Summary 能力和 Transcript 编辑状态机收拢为两个独立深面板。Record 详情页继续承担 Record 查询与生命周期刷新、全资产统一失效、删除、导航、Tab 可用性和标题区能力；完成后，Summary 或 Transcript 的局部改动不再要求修改整个详情页面，同时既有行为仍由自动化回归证明。

**Blocked by:** None — can start immediately.

**Status:** in-review

## 实施顺序

1. 先完成 Summary 面板化，并在不迁移既有测试的情况下保持聚焦门禁全绿。
2. 再完成 Transcript 面板化，并继续保持既有测试全绿。
3. 两个面板稳定后，按页面、Summary、Transcript 的真实职责迁移测试；只迁移、不复制。
4. 最后运行桌面端完整自动化门禁，并明确区分代码级证据与未执行的真实浏览器 / Tauri 验收。

## 验收标准

- [x] Summary 面板完整拥有 Summary 查询与条件轮询、生成与升级、外部处理同意、动作要求与阻塞状态、确认与调整，以及当前 Record 详情内的 Provider 配置交互；页面不再了解这些 Summary 领域分支。
- [x] Summary 面板只从页面接收当前 Record 和语义明确的 Record 资产变化通知；Record 范围的统一失效仍由页面协调，现有 Today 等跨 Feature 失效行为原样保留，不在本票重构其归属。
- [x] Transcript 面板完整拥有 Transcript 与处理任务查询、草稿和来源版本、乐观保存冲突、ASR 外部处理同意、失败重试、高亮与所有转写展示状态。
- [x] Transcript 面板从页面接收当前 Record、高亮目标、显式启用状态和 Record 资产变化通知；只有 Transcript Tab 活动且 Record 未处于删除流程时才启用相关请求，现有门控不得依赖 Tab 组件的挂载细节。
- [x] Record 详情页继续统一负责 Record 查询、404 与加载态、处理期 SSE、降级轮询、窗口聚焦刷新、Record 及派生资产失效、删除期协调、返回课程或 Inbox、标题与导出、Tab 编排和跨 Tab 导航。
- [x] Quiz、知识点和 Todo 既有面板行为与接口不因本票改变；不得引入第二套 Record 生命周期、缓存失效或 Provider 配置体系。
- [x] Summary 生产代码迁移完成后，原 Record 详情聚焦测试、TypeScript 和 ESLint 通过，且既有测试断言不因纯搬迁而改写业务预期。
- [x] Transcript 生产代码迁移完成后，同一组聚焦门禁继续通过；保存冲突、等待同意、失败重试、编辑禁用和高亮展示的既有行为无漂移。
- [x] 测试迁移后，Summary 面板测试拥有 Summary 状态、动作和 mutation 场景；Transcript 面板测试拥有转写编辑、冲突、同意、重试和展示场景。
- [x] 页面测试只保留 Record 生命周期、SSE 与轮询、删除、导航、Tab 可用性、统一失效以及各面板接线冒烟；跨页面与面板的同一场景只能有一个职责归属，不得复制测试。
- [ ] 桌面端完整测试、TypeScript、ESLint、生产构建和格式 / diff 检查全部通过；自动化结果不得描述成真实浏览器渲染、真实 Provider 或 Windows Tauri 运行时验收。
- [x] 本票不统一 Tab 类型与字面量，不新增共享状态 Hook、Context、Controller、事件系统或通用失效服务，不把 Provider 配置归一到 settings 域，也不改变任何产品功能。

## Comments

- 2026-08-29：桌面端全量 19 个测试文件 / 183 个测试、TypeScript 双配置、ESLint、生产构建、改动文件 Prettier 与 `git diff --check` 通过；Standards 与 Spec 复审无剩余发现。
- 全仓 `pnpm format:check` 仍被 63 个本票范围外的既有文件阻塞，本票未批量改写无关文件，因此保留对应验收项未勾选。
- 未执行真实浏览器渲染、真实 Provider 调用或 Windows Tauri 运行时验收。
