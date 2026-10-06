# 04 — 只读查询 + 文档收尾

**What to build:** learning 域薄只读查询能力（未来学习上下文中间件与统计的共同底座），以及 A3 全部文档收尾——数据模型升版、交叉引用同步、进度回写。

**Blocked by:** 03 — 消费循环与证据映射。

**Status:** done

- [x] 薄只读查询：按记录/课程取证据（服务级测试覆盖）；不建独立服务层抽象、不暴露 API 端点
- [x] 数据模型升 v2.6 重命名：event_id 唯一约束的字段级收紧标注、§4.5 A3 已实施标注；全部交叉引用同步（PRD / 技术栈 / GLOSSARY.md / 扩展文档头部，历史「变更记录」行是史实不改动）
- [x] 扩展文档 §40.3 / §40.4 的 A3 行回写「已实施」
- [x] PROJECT_PROGRESS.md 更新（§2 当前阶段、§5 待开发、最后更新行）
- [x] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff

## 落地备注（2026-09-14，commit 0c34e5d feat + 95db699 docs）

- **查询**：`backend/app/modules/learning/queries.py` 薄函数两枚（`list_evidence_by_record` 经 event join——证据表无 record_id 列；`list_evidence_by_course` 直查 course_id），时间升序 + event_id 平局排序；无服务层抽象、无 API 暴露（全库无 router 引用）。spec「按概念」属用户故事 17（Mastery Engine，P4/Out of Scope），按工单口径只做记录/课程。测试落 `tests/test_learning.py` 两例（经真实管道 seed 事件+消费后断言过滤/排序/空集）。
- **数据模型 v2.6**：`git mv` 重命名 + 标题/变更记录新行（v2.5/v2.4 等历史行未动）+ §4.5 头部新增「v2.6 已实施标注」blockquote + learning_events/learning_evidence 表名行加「已实施」+ event_id 标注**唯一约束（v2.6 由普通索引收紧）**。文内「（v2.5，迁移 0020）」等史实标注保留未误改。
- **交叉引用同步**（活引用，grep 实测残留仅 .scratch 历史 spec 与 ADR 史实区）：PRD v2.7 头部、技术栈 v4.5 §、GLOSSARY.md、扩展文档 D9/头部一句话读法/§7 回写/§40.3 A0 行、工作区 AGENTS.md 文档表。
- **扩展文档 §40.3 A3 行**照 A1/A2 样式回写「已实施（2026-09-14，四票完结，ADR-0021）」（含与原「复用 JobRunner」设想的差异）；**§40.4 第 2 步**标 ✅。
- **ADR-0021 落地备注**兑现票 03 承诺：rowid 水位 / 预查幂等+唯一约束兜底 / 3 次尝试口径 / 错误码不入册，四条全录。
- **PROJECT_PROGRESS.md**：最后更新行、§2 行 33（序列加 A3 ✅）、§3 新增「学习事件/证据（A3）」表行、§5 行改为 A3 完结+下一步候选（B1→B2→B5）；另修三处审查发现的既有漂移——F1 两处「现 v2.5」活指针→v2.6、§9 openapi 命令路径 `../../`→`../`（票 02 预告过的笔误，`--check` 曾误报漂移）。
- **门禁**：pytest 446/446（+2 查询测试）、ruff 全绿、pyright strict 0 错、openapi 逐字零 diff（正确路径实测）。
- **审查遗留提示（非本次引入，待用户定夺）**：扩展文档 §3457 行「现以基线 v2.5 为准」为既有过期基线指针（现行 v2.7），不属本票范围未动；`.claude/rules/fastapi.md` §1 业务域清单缺 learning（连同 search/source_anchor、chat→agent 更名）仍待用户批准。
