# 03 — 命令面板：Ctrl+K + 顶栏 🔍 + 混排结果

**What to build:** 应用任意界面按 Ctrl+K 或点顶栏 🔍 按钮（带 Ctrl K 角标）唤起命令面板；空查询显示 3 个捕获命令（开始录音/新速记/新粘贴，Enter 直接触发既有入口）；输入关键词后 250ms 去抖调 /api/search，命令→课程→学习记录→知识点分组混排展示（含 snippet 与所属课程名上下文）；全键盘操作（↑↓ 循环、Enter 确认、Esc 关闭），Enter 跳转（课程→课程详情、学习记录→记录详情、知识点→所属记录详情的知识点页签），跳转后面板自动关闭。本票产出可复用的搜索 hook 与结果项组件（04 复用）。UI 采用 9ui Command（cmdk-base 内核、Base UI 原语，经 shadcn CLI 安装，零 Radix 依赖）。

**Blocked by:** 01（/api/search 契约与 api-types 产物）。

**Status:** ready-for-agent

- [ ] 9ui Command 组件经 shadcn CLI 入库 components/ui，依赖树零 Radix 新增
- [ ] Ctrl+K 为 React keydown 监听硬编码，应用内全局唤起；Esc 关闭；与既有 OS 全局快捷键体系（速记/录音键）互不干扰
- [ ] 顶栏新增 🔍 按钮（Ctrl K 角标）唤起同一面板
- [ ] 空查询显示 3 个命令项，Enter 分别触发开始录音/新速记/新粘贴既有入口
- [ ] 输入后 250ms 去抖请求 /api/search；分组顺序=命令→课程→学习记录→知识点；每类默认上限 5；结果项展示标题/snippet/所属课程名
- [ ] 三类跳转正确（知识点跳记录详情知识点页签），跳转后面板关闭
- [ ] 无结果时明确空态提示
- [ ] zh.json 新增 commandPalette 命名空间，无硬编码文案
- [ ] vitest + RTL + MSW 覆盖：唤起/关闭、键盘循环、命令触发、去抖请求、混排渲染、跳转目标路由 search params

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] Ctrl+K 在焦点位于各输入框/列表的场景下均可唤起且不被输入吞掉
- [ ] 首次搜索无词典加载卡顿（启动预热生效）
