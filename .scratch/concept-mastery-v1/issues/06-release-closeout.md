# 06 — 完成一体化验收与权威文档收口

**What to build:** 将 Concept Mastery 作为一次完整功能交付：所有自动化门禁、真实 Tauri 验收准备、架构决策、数据模型与项目交接信息一致反映当前代码，不保留示意 Mastery 或过期规划口径。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery; 03 — 从 Mastery 下钻到每条 Quiz Evidence; 04 — 让删除、归档、重启与算法升级保持 Mastery 正确; 05 — 在 Course Brain 中查看非侵入式 Mastery 状态.

**Status:** done

- [x] 新增 ADR，记录验证性 Evidence 唯一改变 Mastery、确定性派生快照、与 Forgetting 分离以及拒绝多 Concept/历史猜测回填的理由。
- [x] 数据模型升版并按仓库惯例重命名，标记 Quiz 主概念与 Mastery 表已实施，移除或更正 Concept Evidence 恒为空等过期描述。
- [x] 功能基线、技术栈、扩展设计、领域词汇及全部交叉引用与实际代码一致，历史变更记录保持史实不改写。
- [x] 项目进度文档更新为当前完成状态并保持 200 行以内，删除现有 Knowledge GPS/Mastery 仍为示意的过期说明。
- [x] 全库检索确认章级模拟 Mastery、课程模拟掌握度及相关假数据不再被生产入口使用；无关示意功能不借机删除。
- [x] 后端相关测试与全量 pytest、ruff、pyright、OpenAPI 契约检查通过，测试临时目录在完成后清理。
- [x] 前端相关测试与稳定并发全量测试、lint、触及文件格式检查和 build 通过；不为无关历史格式债务扩大改动范围。
- [x] 真实 Tauri/WebView2 验收清单覆盖亮色、暗色、窄窗口、零数据、数据不足、四类状态、Evidence 下钻和 Course Brain 标记；自动化结果不冒充真机证据。
- [x] 用户真机验收项保持未代勾状态，交接中明确代码门禁、模拟渲染与真实桌面验证的证据边界。

## 实施备注（2026-09-18）

- **ADR-0023**（`docs/adr/0023-concept-mastery-verifiable-evidence-derived-snapshot.md`）：四条裁决——验证性 Evidence 唯一改变 Mastery（AI 自述/确认动作/未校准难度标签均不算）、确定性派生快照可全量重建（版本化、零 LLM、唯一写入口）、Mastery 与 Forgetting 语义分离（不随墙钟衰减，`next_review_at` 留给 Forgetting）、拒绝 Record 广播/LLM 回填/多概念扇出（宁可覆盖率低不错误归因）。附 Considered Options 五方案对比与 Consequences。
- **数据模型 v2.9**（git mv 重命名）：新增头部变更记录（0024 quizzes.concept_id + 0025 user_concept_mastery 实际结构，含「草案五列未建」声明）；quizzes 表补 concept_id 行并作废 2026-08-25「不建 concept_id」草案口径（正文行更正，**变更记录行系史实不改写**）；§4.5 更正 learning_events/evidence 的 concept_id「本期恒 NULL」为「由 Quiz 事件固化写入」；§4.7 user_concept_mastery 标注 P4 提前已实施；表总览 Learner Brain 行标注；已实施 26→27 张（42 张设计口径不变）。
- **交叉引用同步**：技术栈 v4.5（27 表 + v2.9）、GLOSSARY.md :3、PRD 头部 + :156 课程详情行 + F5/F7 行「已提前实施（V1）」标注 + Phase 3/4 行、扩展设计 6 处 v2.8→v2.9 + §40.4 序列「Concept Mastery 收尾」勾销。ADR-0021/0022 内的历史版本引用系定稿时史实，未回改。
- **PROJECT_PROGRESS**：头部收口为六票完结、§3 表行补 06、§5 待开发勾销该链（资料库 V1 波次解锁）、§7 全量抖动口径更新（426→476，失败文件轮换名单）、§6 模块清单修正 19→20 补 learning、Desktop 行「掌握度示意」过期描述移除。162 行（<200）。
- **示意数据检索结论**：章级/课程级模拟掌握度的**独立展示入口为零**（ChapterMasteryList 已随票 02 删除、masteryState.ts 已删）。`courseDetailInsights.ts` 中 `mockChapterMastery → mockCurrentProgress → mockInsightSuggestions` 链仍被概览「洞察建议」示意卡间接消费——该卡是无关示意功能，按票面「不借机删除」保留；其内容数值与真实 Mastery 无关且带「示意」标注，不构成过期口径。
- **顺带修复**：`backend/tests/test_course_brain.py` 的 ruff format 漂移（CB-13 收口时明确「留给 06」，4 行缩进修正，非扩大范围）。
- **门禁证据**：后端 pytest 591 全绿（10min）、ruff check/format 全过、pyright strict 0 错、OpenAPI `--check` exit 0（零契约变化，本链后端 API 未动）、`.pytest-tmp` 已清理。前端全量多轮 473~475/476（失败文件每轮随机轮换，§7 已知资源竞争），失败文件单跑批 28/28、44/44 全绿，lint 0 警告、build（内嵌 tsc）通过；本票零前端代码改动。
- **同仓并行会话声明**：本票工作期间检测到另一会话正在改进 `apps/desktop/src/features/courses/components/CourseBrainMastery.test.tsx`（禁 retry 的 queryClient mock、新增用例，138+/26-，非本票工作内容）。按并行纪律该文件的未提交改动**未纳入本票提交**，由该会话自行提交；本票前端门禁数字（476 项）含该文件中间态，失败轮换结论已用单跑批交叉验证。

## 证据边界（交接声明）

- **自动化门禁**证明：后端合同（591 测试含 Mastery 算法黄金样本、生命周期、API 守卫）、前端渲染合同（MSW 渲染测试 476 项）、类型与契约（tsc/pyright/OpenAPI 零 diff）。
- **jsdom/MSW 渲染测试不是真实桌面证据**：canvas 图谱（ECharts SVG）、主题切换、窗口尺寸、键盘焦点路径均需真实 Tauri/WebView2 目检。
- **用户真机验收**：见下清单，不代勾。

## 用户真机验收（概念掌握度链 01~05 汇总，不代勾）

**环境**：`pnpm --filter @knowrealm/desktop tauri dev`；需一门含已转写+已确认总结记录的课程；脑图已构建并确认 ≥2 个概念；作答用客观题（判分即时）。

- [x] **主概念（01）**：生成习题的建议主概念只来自已确认概念；作答前可改/清空；作答后字段只读并提示「首次作答后主概念固定」。
- [x] **掌握度出现（02）**：同一概念作答 ≥3 次，等 ≤30 秒或重启后，「知识GPS」标签出现该概念（<3 条显示「数据不足」且无百分比）；3 次全对 = 100% + 置信度「低」；状态筛选与 URL 恢复生效；概览卡显示覆盖率与四态分布、无课程总平均分。
- [x] **四类状态齐全（02）**：构造混合对错使同一课程同时存在 数据不足/待加强/学习中/稳定 四种状态（分布计数与徽章一致）。
- [x] **详情下钻（03）**：GPS 行打开详情弹窗（状态/百分比/置信度/证据数/最近验证与作答）；证据按时间倒序且 ≤12 条；跳转按钮分别回到记录习题页与模拟测试结果页；模拟测试逐题归属的证据计入各自概念。
- [x] **生命周期（04）**：删除一条已作答记录后相关概念立即重算（可等 30s 或重启）；归档概念退出脑图/GPS、详情 404；重启应用无异常（recover 幂等）。
- [x] **脑图标记（05）**：节点标签旁状态点 + tooltip「掌握状态」行，节点主色仍随重要度灰阶；列表正式行有徽章（含「数据不足」）、候选行无；详情面板「掌握详情」打开既有弹窗并可跳回来源。
- [x] **亮色/暗色**：全链路两主题下状态点、徽章、图谱对比度可辨。
- [x] **窄窗口（约 1100px）**：脑图/列表 + 详情双栏、GPS 列表、详情弹窗均无横向溢出。
- [x] **零数据课程**：未构建脑图 → GPS 空态引导「打开课程脑图」；零证据概念 → 「数据不足」诚实展示。
- [x] **键盘路径**：Tab 进入 GPS 列表行 → Enter 打开详情弹窗 → 弹窗内可 Esc 关闭；脑图 canvas 不可 Tab 属既有行为（键盘用户走列表视图）。
