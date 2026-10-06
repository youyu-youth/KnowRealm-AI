# 16 - 复习资料

> Wave: B ｜ PRD: §4.4.2 复习资料行 ｜ 决策引用: 2026-09-06 plan grill 定稿（生成上下文、确认/编辑/版本链、LangGraph、超长窗口自适应；数据模型已升 v2.3 同步）

## 功能描述 / 目标

Record 级三段式复习资料的生成与定版：考前速记 + Top 重点清单 + Markdown 大纲树。基于**转写/文档解析全文 + 已确认总结**生成（不走"总结+KP"路线），弹窗 HITL 工作台完成确认 / 反馈调整 / 手动编辑，接入 10 的导出通道。

## 功能范围

**做**：
- 生成上下文 = **转写/文档解析全文为主 + 已确认总结作辅助**；KP 不进上下文；课程 learning_context / 深度字段照总结规则注入；输出中文
- 三段式产出：考前速记（Markdown，可含代码块；程序员场景默认含代码速查块）、Top 重点清单（`key_list_json`，条数不固定由 LLM 按内容密度决定，prompt 给区间约束）、Markdown 大纲（纯标题层级树 + 叶子短语，禁代码块/表格）
- **LangGraph 编排**（照总结同构）：generate → review[interrupt] → 条件回 generate；AsyncSqliteSaver 复用 `langgraph.db`（thread_id 前缀隔离）；调整经 `Command(resume="ADJUST")` 恢复。KP/习题/Todo 维持直接 LLM 不动——LangGraph 只进"多版本 HITL 循环"型资产（总结、复习资料）
- **弹窗 HITL 工作台**：生成完成弹窗预览三段，弹窗内【确认】/【反馈调整（不限次）】/【手动编辑】；关闭后 tab 常驻阅读态展示当前内容，操作重开弹窗
- **手动编辑就地生效不换代**：速记/大纲用 Markdown 源码 textarea，重点清单条目编辑器（增删改）
- 版本链：仅 AI 重生成产生新版本（version_no 递增），旧版 SUPERSEDED；只读版本列表 + 查看切换（照总结先例），无一键回滚
- 大纲树形渲染：自建可折叠树（按标题层级递归，默认全部展开）
- Markdown 渲染统一组件（放 `src/components/` 供复用）：react-markdown + shiki 转正（两者已在 package.json 声明，零新增依赖）；shiki css-variables 主题接 `.dark` 双主题
- 接入 10：**仅 CONFIRMED 版本可导出**；单 Tab 导出默认名 `{Record标题}-复习资料.md`；聚合位次已定（Summary→知识点→习题→复习资料→Todo）；复习资料段不转义，保留 Markdown 与代码块语义
- 转写过期联动：行记 `transcript_source_version`，转写已改则拒绝新提交并提示；已生成内容不删不覆盖，前端提示"转写已更新，可重新生成"

**不做**：
- 图形化思维导图导出、遗忘曲线驱动的复习排期（P4 遗忘雷达）、复习队列（P4）
- RAG 检索式生成（已否决：选择性召回 vs 全覆盖浓缩不匹配 + 撞静默截断红线 + 向量基建是 P2/P3 chat 域档期）
- 版本一键回滚（想用旧版内容 = 复制后手动编辑）
- 新增 learning_event（PRD #43 事件集不扩；导出不产生事件为 10 既定）

## 核心业务流程

总结已确认（record COMPLETED）→ 复习 tab → 生成 → 弹窗 HITL 工作台（三段预览：确认 / 反馈调整重生成 / 手动编辑）→ 确认定版 → tab 常驻展示（可重开弹窗继续调整/编辑）→ 可导出 `.md`

### 状态机

- `GENERATED → CONFIRMED`（用户确认，confirmed_at 落行；确认不锁编辑）
- 反馈调整/重新生成 → 新版本 GENERATED，旧版本 SUPERSEDED
- 手动编辑不触发状态迁移（就地更新当前版本内容）
- 解锁闸门 = 总结已确认（PRD §4.4.2"总结确认后按需触发"，同 quiz/todo tab 解锁条件）；ARCHIVED 课程三道闸门照抄

### API 草案（照总结镜像）

- `GET /api/records/{record_id}/review-material`（当前版 + action_required / blocked_reason / active_job_id）
- `GET /api/records/{record_id}/review-materials`（版本列表，只读回看）
- `POST /api/records/{record_id}/review-material-jobs`（首生，202）
- `POST /api/records/{record_id}/review-material-adjustments`（反馈调整，绑当前 GENERATED 版本，feedback 1~1000 字，202）
- `POST /api/records/{record_id}/review-material-confirmations`（确认）
- `PATCH /api/records/{record_id}/review-material`（手动编辑，就地生效）

## 关键业务规则

- **超长按模型窗口自适应**：生成前估 token——装得下全文单次调用；装不下按语义段落分块 map-reduce 分级（照总结 #36 模式）；任何情况禁止静默截断/丢段。总结域 3 万字硬阈值不动，本策略仅复习资料域
- prompt 留痕：PROMPT_VERSION 常量（review-v1 / review-adjust-v1 风格）随行 + `llm_call_logs`；token_usage / latency 照 ai_summaries 行上留痕；**输出全文不进日志**
- `transcript_source_version` 过期锚点：submit 时校验，转写已改 → 拒绝并提示先看新总结（照 KP 的 PREREQUISITE_CHANGED 闸门风格）；`generated_from_summary_id` 仅溯源，总结换代不阻塞
- UI 文案一律"考前速记"全称，与捕获入口"速记（Quick Note）"区分（GLOSSARY.md 已增术语）

## 数据与迁移

- 新迁移 0017 建 `review_materials`（数据模型 v2.3 全列，见该文档 §4.3）
- `processing_jobs` 重建扩 job_type CHECK（REVIEW_MATERIAL_GENERATION）+ one-active 部分唯一索引（照 0016 模板）；同步顶 6 处 user_version 断言
- 后端 schema 变更后重跑 `packages/api-types` 类型生成

## 前置依赖

- 06（总结已确认——解锁闸门与辅助上下文）、10（导出通道）；07 不再是上下文依赖

## 验收标准（出口线）

- [ ] 基于转写全文 + 已确认总结生成三段式复习资料（KP 不进上下文）
- [ ] 弹窗 HITL：确认 / 反馈调整重生成（不限次）/ 手动编辑三操作可用
- [ ] 反馈重生成产生新版本、旧版 SUPERSEDED；版本列表可回看切换
- [ ] 手动编辑就地生效不换代（速记/大纲源码编辑、重点清单条目增删改）
- [ ] 大纲树可折叠展开、层级正确、默认全展开
- [ ] 含代码块时高亮渲染正确（亮 / 暗双主题）
- [ ] 超长转写走窗口自适应：全文装得下单次、装不下分级，无静默截断
- [ ] 转写更新后新提交被拒绝并提示；已生成内容不删不覆盖
- [ ] 导出仅 CONFIRMED 版本、与界面内容一致（保留 Markdown 与代码块语义）
- [ ] ARCHIVED 课程无法生成复习资料
- [ ] （用户真机验收）弹窗 HITL 工作台与三段阅读体验
