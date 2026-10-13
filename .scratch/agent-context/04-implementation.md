# 04 固定内容与来源有效性实施记录

实现基点：`d9de3889136270e3e877c98e6cbec8e80086ad33`，当前分支 `feat/extend-dev-09`。用户已有 `.scratch/agent-context/baseline/` 保留。本文只记录 04，不关闭 05/06。

## 实现

- 迁移 0049 只增加 DDL：设置、轮次输入与实际模型请求各保存 `pins_json`。已有会话默认空固定项，不重写历史或启动摘要。
- 支持短文本、明确约束/决定、原消息或资料片段，以及资料对象优先取材。片段匹配真实来源、完整来源版本与原始偏移；对象正文从当前有效版本限长选材。
- 页面 POST `/api/chat-sessions/{session_id}/context/pins` 与 Agent `change_context_pin` 使用同一个领域核心。页面显式操作写 USER_MANUAL 回执；Agent 注册 L1、OP_CONTEXT_PIN，复用三档、Proposal、受控提交、取消/身份校验及幂等效果。
- `get_context_settings` 返回当前设置版本及固定身份，复用共享次数/字符预算，并有分页。失效来源只返回身份和原因，不向模型返回缓存正文或正文型标题。
- 新轮次受理时冻结固定设置。恢复读取原快照；页面调整只影响下一轮。正在压缩的旧轮可使用旧快照，但版本变化后不能激活为新会话摘要。
- 页面和 Worker 共用 `select_pinned_material`：固定块参与选材计量，可缩材料让位；有效短文本/片段不自动截断。必需输入无法容纳时摘要与回答均不出网，保留已受理提问及全部固定设置。
- 来源原文作为数据，不能授权执行。固定不写 Learner Memory，不扩大作用域。原挂载对象失效仍由原发送闸门拒绝。
- 原文、legacy 工具读取、分栏摘要在读取/激活/模型边界重验来源；失效摘要不再自动注入。设置/写操作工具历史、调用参数及供应商原始参数副本同样投影校验；失效时清正文/预览，保留调用配对、成功回执身份和持久事实。当前页保留失效固定项及原因，允许更新/解除。
- 页面区分下一轮设置与最近请求实际注入：实际来自持久请求记录，不由当前设置推断。文本编辑冻结预期版本；来源更新绑定进入编辑时的版本，显式重试或成功后才采用新版本。
- 已同步 OpenAPI/TS、三项错误码、zh/en、确认卡/直执行回执与过程文案。图协议升为 v5；旧在途协议继续沿既有不兼容等待/停止重问流程，不强行续跑。

## 验收边界

| 层级 | 路径与证据 |
| --- | --- |
| 自动化、真实 API/SQLite/Worker | `backend/tests/test_context_pins.py` 使用公开 ChatTurn、迁移 SQLite、原 JobRunner/框架，只有模型边界替身。覆盖长历史、压缩、固定超限、三档、确认失效、并发写、运行/恢复、来源版本/归档/删除/共享解除、材料让位、legacy 原文与对象当前版本、迟到摘要/取消。 |
| 前端自动化 | `src/pages/chat.test.tsx` 和确认卡测试通过公开页面/API（MSW 边界），验证固定/编辑/解除、来源身份/偏移、实际页与配置页区分、确认及持久结果显示。 |
| 真实 HTTP + 浏览器 + SQLite/Worker | 隔离数据目录 `backend/.tmp/04-live-browser-data`；真实 localhost HTTP，Tauri 桥接及模型为替身，未改用户数据。页面固定 → SQLite USER_MANUAL 回执 → 真 Worker 完成 → 实际输入页查到同版本已注入；来源页搜索、读取、固定原文片段也真实落库。 |
| 浏览器视觉模拟 | 真实页面组件；四主题、英文、640×800、200% 字号，无横向溢出；键盘 Enter 切换实际页，固定提交成功。视觉数据替身与上述真实 HTTP 证据分开。不是 Tauri/WebView2 或 Windows 系统缩放。 |
| 未验证 | 真实模型语义/供应商用量、真实 Tauri/WebView2、Windows 125%/150% 缩放及完整 reduced-motion，留 06。 |

真实 HTTP 示例：会话 `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`；轮次 `a37c5c2e-6abc-48cc-bf1e-214dcebb285f` 完成，冻结版本 2，固定 `afdb2486-7a04-4cae-a467-328ca783ba51` 原文进入实际输入，usage 缺失保持未知。来源片段 `record:d0000000-0000-4000-8000-000000000011` / 版本 1 / 偏移 0，固定后设置版本 3；解除短文本后版本 4，旧实际请求仍保留其注入事实。

## 长历史与语义边界

`test_pin_survives_long_history_and_unpin_changes_next_turn` 连续 12 轮验证独立固定原文每次进入模型输入；解除后下一轮停止注入。`test_pins_survive_compaction_without_entering_summary_input` 在 16 个完整往返触发真实压缩，固定独立原文未进入摘要输入且仍进入后续回答输入。证明的是确定性输入保留，不保证模型遵守或理解无误。未固定摘要仍可能遗漏语义细节，须受限取回原文；本票未声称摘要语义无损。

## Code Review

按 code-review skill 分 Standards / Spec 两轴只读复核。初审发现的来源更新重试旧版本、选材未计入固定块、legacy 读取失效、页面预估不一致及历史设置工具/调用参数副本绕过失效均已修复，复审两个轴无未关闭发现。相关公开 Worker 回归证明执行/预估一致与来源递归验证。

## 检查结果

- 相关后端原文取回/预算/错误登记组合：21 项通过，`.pytest-tmp-runs/20261013T121247Z-dbc21bf9/backend/result.json`。
- 固定新增首批完整回归：12 项通过，`.pytest-tmp-runs/20261013T122351Z-91cf40ed/backend/result.json`；恢复原固定快照通过，记录在下一次 14 项组合中。
- 选材让位（含页面预估）与 legacy 来源/对象当前版本两项通过，`.pytest-tmp-runs/20261013T123958Z-2a9ee63e/backend/result.json`。
- 改动范围门禁已通过：ESLint、Prettier、两份 TypeScript、Vite、Ruff/格式、Pyright 0 错误；日志 `04-check-changed-final.log`。最终全部改动已重新通过相同范围门禁；API 契约 `pnpm --filter @knowrealm/api-types check` 通过。
- 最终全量已完成：前端 735 通过 / 8 失败，后端 1258 通过 / 13 失败；原始记录 `.pytest-tmp-runs/20261013T125158Z-e3f53ee0/`，整体 FAILED。
- 固定功能最终 19 项均通过（含两档历史工具缓存/调用参数副本回归），`.pytest-tmp-runs/20261013T140544Z-56731f3c/backend/result.json`。同批三项旧摘要夹具缺 sources 导致失败；已补合法夹具并单独复测三项全通过，`.pytest-tmp-runs/20261013T141057Z-a7ddec3a/backend/result.json`。
- 相关前端四文件 113 项全通过，`.pytest-tmp-runs/20261013T140815Z-7786cb33/frontend/result.json`。全量中两条新增页面失败是切 Tab 后过早断言/后续页面初始化时序，修正公开状态等待后闭环通过。
- 基点 `E:/workspace/project/my/KnowRealm-AI-context04-baseline-d9de388` 独立 frozen pnpm/uv 安装成功。后端同 13 节点复测 10 失败 / 3 通过，记录 `.pytest-tmp-runs/20261013T141552Z-2bf27182/backend/`（该目录在基点 worktree）。三项通过对应本次已修复的摘要夹具缺 sources；其余 10 失败在基点重现。
- 本次将已受影响的挂载工具精确清单与普通/研究提示词版本断言同步到当前装配；长材料旧例从泛化 budget 断言改为来源变更优先失效的明确 `CONTEXT_SOURCE_STALE`，预算无出网验收仍由专用用例覆盖。四项本次受影响断言最终复测全通过，`.pytest-tmp-runs/20261013T142538Z-5c292cd7/backend/result.json`。
- 保留历史失败：迁移旧库夹具遗漏 chat_compactions、十轮尾裁断言、过程文本旧断言、document_import 私密错误日志、quiz_last_count 新主题字段、second_sidecar 10 秒超时。日志/错误泄露属于已有实际风险，本票未修改无关模块。

## 临时资源

测试运行记录保留于 `.pytest-tmp-runs/`，数据库使用运行器独立 basetemp。隔离浏览器和 Vite/HTTP 服务只用于本次验证，已关闭自建浏览器页和进程、删除辅助脚本；用户原有 baseline 与其他进程不改动。隔离数据不纳入提交。新建独立基点 worktree 与日志保留供复核，不复用用户已有 baseline。

## 基点前端比较

四个剩余失败文件在独立基点复测 35 项：30 通过 / 5 失败，记录 `E:/workspace/project/my/KnowRealm-AI-context04-baseline-d9de388/.pytest-tmp-runs/20261013T142043Z-59b7343e/frontend/`。复现 RecordDetail 旧 review 布局断言、LearningPlanTab 三项只读/选择器断言和 CommandPalette 关闭时序断言。QuizTests 第三个 tab 历史用例基点通过；全量中该项失败未稳定复现，当前工作区单独复测该文件 4 项全通过，`.pytest-tmp-runs/20261013T142731Z-e8d4eb8f/frontend/result.json`；保留全量偶发/资源时序不确定项，不声称已修复。
