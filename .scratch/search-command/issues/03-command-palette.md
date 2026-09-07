# 03 — 命令面板：Ctrl+K + 顶栏 🔍 + 混排结果

**What to build:** 应用任意界面按 Ctrl+K 或点顶栏 🔍 按钮（带 Ctrl K 角标）唤起命令面板；空查询显示 3 个捕获命令（开始录音/新速记/新粘贴，Enter 直接触发既有入口）；输入关键词后 250ms 去抖调 /api/search，命令→课程→学习记录→知识点分组混排展示（含 snippet 与所属课程名上下文）；全键盘操作（↑↓ 循环、Enter 确认、Esc 关闭），Enter 跳转（课程→课程详情、学习记录→记录详情、知识点→所属记录详情的知识点页签），跳转后面板自动关闭。本票产出可复用的搜索 hook 与结果项组件（04 复用）。UI 采用 9ui Command（cmdk-base 内核、Base UI 原语，经 shadcn CLI 安装，零 Radix 依赖）。

**Blocked by:** 01（/api/search 契约与 api-types 产物）。

**Status:** done

- [x] 9ui Command 组件经 shadcn CLI 入库 components/ui，依赖树零 Radix 新增
- [x] Ctrl+K 为 React keydown 监听硬编码，应用内全局唤起；Esc 关闭；与既有 OS 全局快捷键体系（速记/录音键）互不干扰
- [x] 顶栏新增 🔍 按钮（Ctrl K 角标）唤起同一面板
- [x] 空查询显示 3 个命令项，Enter 分别触发开始录音/新速记/新粘贴既有入口
- [x] 输入后 250ms 去抖请求 /api/search；分组顺序=命令→课程→学习记录→知识点；每类默认上限 5；结果项展示标题/snippet/所属课程名
- [x] 三类跳转正确（知识点跳记录详情知识点页签），跳转后面板关闭
- [x] 无结果时明确空态提示
- [x] zh.json 新增 commandPalette 命名空间，无硬编码文案
- [x] vitest + RTL + MSW 覆盖：唤起/关闭、键盘循环、命令触发、去抖请求、混排渲染、跳转目标路由 search params

**实现备注（2026-09-07，agent 交付）：**

- 安装：components.json 登记 `@9ui` registry 后 `pnpm dlx shadcn@latest add @9ui/command`，CLI 提示覆盖 dialog 时拒绝（项目 dialog 为定制版且 API 兼容），仅新增 `command.tsx` + `cmdk-base` 依赖（依赖树仅增 cmdk-base/@base-ui/utils，零 Radix）。components/ui/command.tsx 保持 registry 原版未手改（desktop-ui.md §2）；面板在 feature 层用 `Dialog + Command shouldFilter={false} loop` 自组合（ui 的 CommandDialog 不透传 shouldFilter，服务端 FTS5 检索必须关客户端过滤）。
- 复用资产（04 资产库直接用）：`features/search/api/queries.ts` 的 `useSearchResults(query, limit?)`（内置 250ms 去抖、空查询不请求、limit 省略走后端默认 5）；`SearchResultItem`（纯展示：图标/标题/snippet/课程名上下文，不绑 cmdk 可在普通列表复用）。
- 行为裁决落地：命令项查询期保留并按文案子串过滤（spec「命令项与三类资产同屏混排」）；空分组不渲染标题（shouldFilter=false 时 cmdk Group 恒渲染，需自行按长度条件渲染，已测）；重开面板查询重置（关闭时清空，选中跳转/命令触发/Esc 三路统一走同一 close 包装）；Ctrl+K 排除 Alt/Shift/Meta 组合防误吞 OS 全局键（Ctrl+Alt+K 不唤起有测试）。
- 命令入口复用 AppShell `openCapture`（3 命令=顶栏按钮同源）；跳转：课程→`/spaces/:id?tab=overview`（路由 search 必填）、记录→`/records/:id`（默认 summary 页签）、知识点→`/records/:recordId?tab=knowledge-points`。
- 测试基建：setup.ts 补 ResizeObserver/scrollIntoView stub（jsdom 缺失，cmdk-base 必需）；mocks/handlers.ts 补 PUT /api/settings/preferences（AppShell last_route 记忆在全 App 测试中的未拦截噪音）。12 用例全绿；全量 330/331（唯一失败 SidebarUserArea「有昵称与头像」为分支 HEAD 既有失败，暂存本次改动后仍复现，与本票无关）。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] Ctrl+K 在焦点位于各输入框/列表的场景下均可唤起且不被输入吞掉
- [ ] 首次搜索无词典加载卡顿（启动预热生效）
