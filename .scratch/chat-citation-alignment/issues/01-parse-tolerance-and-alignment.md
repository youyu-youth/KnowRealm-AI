# 01 — chat 引用角标不可点：解析容错 + 意译摘录模糊对齐

**What to build（缺陷修复）:** 用户实测挂载会话（deepseek-v4-flash）回答带 [1]~[9] 角标但全是纯文本、点击无跳转。库内取证定位双重根因：① 模型把文末引用块输出为 markdown blockquote `> [n] …`，`CITATION_LINE_RE` 只认行首 `[n]` → 整块不识别、citations=[] 落库（全库 10 条助手消息 citations 全空，普遍现象）；② 9/9 摘录是意译改写而非转写原文连续子串，`quote in transcript` 严格校验即使过了格式关也会全丢（docker 文档 5.8 万字 > 3 万上限只喂摘要+知识点，意译被结构性放大）。前端 CitationBubble 与跳转链路无缺陷。

**Status:** done

- [x] 解析容错：`CITATION_LINE_RE` 接受行首 markdown 前缀（`>` / `-` / `*` 可组合），尾部连续行扫描语义不变（引用块后仍有正文行则整块不识别）
- [x] 模糊对齐 `_align_quote`：摘录逐字命中失败（意译或超 80 字）时，归一化（去空白与 `**`）后按转写行 `SequenceMatcher`（real_quick_ratio 预筛）取最佳相似句，≥0.65（`CITATION_ALIGN_MIN_RATIO`）则以**真实原句**替换展示（超 80 字时以最长公共片段为锚取 ≤80 字窗口）——落库 quote 必然来自 transcript，前端「分片 content 包含 quote」句级定位天然必中；低于阈值诚实丢弃（DESIGN.md 不伪装引用）
- [x] `parse_citation_reply` 校验链：精确命中直接保留 → 否则对齐替换；补 `index >= 1` 过滤（与 API 侧 `ChatCitationOut.ge=1` 对齐，消灭 [0] 落库后被读取层静默丢弃的缝隙）；函数签名不变、message_service 调用点零改动
- [x] 提示词加固：明确「行首直接以 [n] 开始，不要使用 >、- 等 markdown 前缀」「逐字连续出现的原文（不改写、不概括）」+ 引用块示例；`CHAT_PROMPT_VERSION` bump `chat-mount-cite-v2`
- [x] 测试：单元新增 6 例（blockquote/列表前缀识别与剥离、意译对齐替换为真实原句、无关摘录丢弃、[0] 丢弃、>80 对齐 ≤80 窗口）+ 既有用例语义更新（>80 从「直接丢弃」改「对齐救回」）；集成新增 blockquote 意译回答 → citation 事件下发替换后原句、历史接口 citations 正确
- [x] 门禁：backend pytest 421 passed（--basetemp=.pytest-tmp）+ ruff + pyright 全绿；前端与 API 契约零改动（citations 结构未变）

**范围外：** >3 万字转写喂检索式材料（模型看不到原文的结构性问题）→ A1 检索工具票；本次靠对齐层兜底（摘要派生句相似度高可对上），不强求 100% 救活。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 重启应用后在 docker 等挂载会话重新提问，回答角标 [n] 可点击、引用列表可见，点击跳转转写页定位到句子（音频记录带时间戳徽章）
- [ ] 历史存量回答（修复前生成的）角标仍为纯文本属预期——citations 在生成时落库，不回填
