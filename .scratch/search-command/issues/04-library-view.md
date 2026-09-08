# 04 — 资产库视图（/library）

**What to build:** 左栏资产库入口（既有禁用占位）激活为独立路由：搜索优先形态——搜索框 + 类型过滤 Tabs（全部/学习记录/知识点/课程）+ 分组结果列表，空态走 #42 引导卡、无结果明确提示；复用 03 的搜索 hook 与结果项组件，传更大的每类 limit，类型过滤在展示层取对应组；点击跳转与面板同口径。

**Blocked by:** 03（复用搜索 hook 与结果项组件）。

**Status:** done

- [x] 侧栏资产库入口激活，路由 /library 可直达且参与上次界面恢复（设置页/首启向导既有豁免规则不变）
- [x] 搜索框输入后去抖调 /api/search，传更大每类 limit
- [x] 类型 Tabs（全部/记录/知识点/课程）在展示层过滤对应组，切换即时生效
- [x] 空查询显示 #42 空态引导卡（非空白）；有查询无结果显示明确提示
- [x] 结果点击跳转与命令面板同口径（知识点→所属记录详情知识点页签）
- [x] zh.json 新增 library 命名空间，无硬编码文案
- [x] vitest + RTL + MSW 覆盖：空态引导、类型过滤、无结果提示、跳转目标路由 search params

**实现备注（2026-09-08，agent 交付）：**

- 结构：`pages/library.tsx`（validateSearch 承载页签）+ `features/library/LibraryPage.tsx`；AppShell `nav.library` 补 `to: "/library"` 即激活，禁用 Button 分支只剩学习画像。上次界面恢复零改动自动覆盖 /library（AppShell 仅豁免 /settings；首启向导豁免在 `__root.tsx` beforeLoad，均未动）。
- 页签是 URL 状态（.claude/rules/desktop-react.md §4 硬性要求，code-review 抓出后整改）：`?tab=records|knowledgePoints|courses`，缺省=全部且参数省略，切换 `replace: true` 不新增历史；因经 navigate 异步落地，切页签"即时生效"在展示层取分组实现，不重发请求（测试断言 searchRequests 恒为 1 并断言 URL search params）。
- 复用：`useSearchResults(trimmed, 50)`（50=后端 limit 校验上限 le=50，面板默认 5）；结果行 `ResultRow` 包普通 button 复用 `SearchResultItem`（组件头注释预留的用法）；跳转三函数与 CommandPalette 同口径。跳转函数未与面板下沉共享（两处小而稳定，抽共享会动已验收的 03 代码，违反精准修改）。
- 展示细节：分组顺序=学习记录→知识点→课程（与页签序一致；面板为课程→记录→知识点，两视图无一致性约束）；分组标题用 h2 保持 h1→h2 语义层级；空查询隐藏 Tabs 只显 #42 引导卡（无可过滤内容，Tabs 无意义）；「该类型下没有匹配结果」提示覆盖"总结果>0 但当前页签空组"；错误态+重试按钮为必要边界（isError 且无数据时不拦截会永久停在 loading 态）。
- 测试：10 用例全绿（jsdom 下 App 挂载异步，输入框查询用 findByRole）；全量 340/341，唯一失败仍为 SidebarUserArea「有昵称与头像」既有失败（工单 03 备注已记录，干净 HEAD 复现，与本票无关）；TodoPanel 全量跑间歇超时为既有抖动。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真实数据下资产库独立完成跨课程检索，体感流畅
