# 05 — 来源时间轴前端与 chat 句级定位

**What to build:** 学习者在课堂详情转写页看到句级来源时间轴：浏览态从纯文本升级为行式时间轴（左时间戳 mm:ss、右句文本，密集排布），无时间戳分片正常陈列（无时间标记），粘贴 / 速记等无分片记录回落纯文本；编辑态维持现有整篇文本编辑不变。chat 回答的引用角标点击后跳到转写页并定位到包含该摘录的句子（滚动 + 高亮 + 时间戳徽章），原文已变动时维持现状明确提示。本票纯前端，后端 citations 契约零改动。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 02、03、04（三种数据形态——带时间戳转写分片 / 文档分片 / 无时间戳分片——真实就绪）。

**Status:** done

- [x] TranscriptPanel 浏览态 = 行式时间轴：一次拉取全量分片渲染；时间戳 mm:ss 格式；无时间戳分片无时间标记陈列；设计遵循 DESIGN.md 与设计令牌分层（impeccable 规范，优先复用 shadcn / 既有组件）
- [x] 无分片记录（粘贴 / 速记）浏览态回落纯文本展示（现状形态）；加载 / 空态 / 错误态处理与既有面板模式一致
- [x] 编辑态维持整篇 Textarea 与既有保存流程（乐观锁、错误提示）完全不变；编辑保存后重新拉取分片呈现对齐结果
- [x] chat 引用角标点击跳转：在已加载分片中匹配 quote（分片 content 包含）→ 滚动到该分片 + 高亮 + 时间戳徽章；多命中取首 match；匹配失败走现状「原文已变动」兜底
- [x] zh / en 文案同步（i18n key 两边一致，一致性防线过）
- [x] MSW 组件测试：三形态渲染（时间戳 / 无时间戳 / 纯文本回落）、quote 定位与兜底、编辑态不受影响；vitest / tsc / prettier 全绿
- [x] 后端零改动验证：openapi 导出零漂移

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真机课堂详情看到时间轴；点击 chat 引用角标跳转定位到句子并显示时间戳

**实施备注（f8212d7）：**

- 三态浏览视图（TranscriptPanel 非编辑分支）：分片 pending → 行内 Spinner + 「正在读取来源分片」；有分片 → `SourceTimeline` 行式时间轴（左列时间戳 12px tabular-nums muted、右列句文本，发丝线 divide-y；无时间戳分片保留等宽占位列维持文本基线，整列表无时间戳时不留列）；无分片或分片读取失败 → 回落既有 `TranscriptView` 纯文本（分片是派生定位层，读取失败不阻断正文阅读；quote 在回落态仍可整篇定位）。
- 时间戳格式：不足 1 小时 `mm:ss`，≥1 小时 `h:mm:ss`（对齐 DESIGN.md §10「录音与音频时长用 mm:ss / h:mm:ss」；spec「左时间戳 mm:ss」按此理解，票 6 文档落盘时同步标注）。
- quote 定位：`findIndex(content.includes(quote))` 多命中取首；命中分片行 `scrollIntoView({block:"center"})` + 摘录 `<mark>` 内联高亮（与 TranscriptView 同一引用高亮语言，aria-label「引用定位」）+ 左列时间戳升级为 primary 徽章；命中分片无时间戳则只高亮无徽章；分片均不包含 → 既有「原文已变动」提示。
- 分片重拉时机：保存成功（onSuccess invalidate transcriptSegments）、409 后「载入最新版本」（reloadTranscript refetch）、RecordDetailPage.invalidateRecord 补同 key 失效覆盖 SSE / 窗口聚焦刷新。
- API 接线：`recordApi.getTranscriptSegments` + `recordKeys.transcriptSegments`；查询 enabled = 面板启用且转写 READY。
- i18n 新增 `record.detail.transcript.timelineLabel` / `segmentsLoading`（zh/en 同步，一致性防线过）。
- 测试：TranscriptPanel 7→12 用例（时间轴三形态、多命中取首定位 + 徽章 + 滚动、兜底、编辑保存重拉），既有 READY 用例与 App.test.tsx 导入用例补空分片 mock 维持回落形态断言。
- 门禁：vitest 386/387（唯一失败「今日页 > 无待办时不显示空态文案，读取失败可重试」经 stash 基线验证为分支存量问题，与本票无关）；tsc / prettier / api-types openapi --check 全绿。
