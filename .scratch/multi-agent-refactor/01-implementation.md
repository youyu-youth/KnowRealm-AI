# 01：general / knowledge 独立入口实施记录

日期：2026-10-21。实现已完成；双轴评审修正已复查通过；工单 ready-for-human。全量保留一项基点可复现失败，真实模型与原生桌面验收未执行。

## 范围与授权

- 用户本轮明确要求使用 implement 完成 01，作为原 Q5 的实施授权；Q1～Q4、Q6～Q9 不变。
- 基点 `202a4c89267963d818cfc449dcb59931973404d9`；开工工作区干净；当前分支 `feat/multi-agent-refactor`。实现提交 `2648ab6`，评审修正 `d15dd33`，输入准入/来源状态断言补强 `bb76bd7`。
- 本票只交付两个独立入口；02～04 的委派、共享父子预算、子执行持久化和协作进度尚未实现。
- 没有修改 rules、历史迁移、真实用户数据或供应商配置，没有新增依赖、任务循环和业务操作账本。

## 实现与兼容

- 0056 仅 DDL：`chat_sessions.agent_id TEXT NOT NULL DEFAULT 'general' CHECK (...)`。旧行在升级后读取 general，历史消息原样保留；ORM、请求/响应、创建/列表/详情贯通。
- `GET /api/agents` 返回两项静态目录：id、purpose、read_only；沿用启动令牌校验。未知身份由现有 422 防线拒绝；PATCH 不接受身份；异常持久身份拒绝执行，不回落 general。
- general 保留原工具；knowledge 在有效非 FREE 范围仅挂 `search_library`。FREE 仅分析直接提供文字，专业提示解释缺少来源；任何 mode/auth_mode 均不挂联网、业务写工具、提案、上下文修改、文件或委派。
- KnowledgeToolGuardMiddleware 同时约束实际工具执行，拦截模型猜测的内置工具；原取消、工具身份、预算、输入/输出治理及模型工厂继续复用。
- 配置拼装使用 `dataclasses.replace` 保留 tools/subagents/skills/backend/middleware 五个扩展点。预算预览与执行均按固定 Agent 身份选择同一工具面；测试同时比较公开 estimates 的 tool_count 与真实请求估算记录。
- knowledge 的输出复用原引用解析，关闭 web 分流：含 URL 的摘录继续按本地原文校验，伪造网络引用拒绝；引用块照常剥离，FREE 同样处理伪造引用；general 解析行为不变。
- 聊天图版本升至 `chat-graph-v11`。旧在途轮次沿现有版本兼容流程停止后新问，不把不同工具结构的 checkpoint 直接续跑。
- 新建菜单从真实目录选择助手，再选原资料范围；记录挂载创建复用统一 mutation。当前会话的 FREE/RECORD/COURSE/ALL 范围切换保留身份；原课程、资料、知识点 CTA 省略身份时仍为 general。
- 列表和标题持续显示身份；knowledge 联网开关禁用并解释原因，授权档入口显示只读说明。zh/en 同 key；OpenAPI/api-types 已重新生成，无新增 HTTP 错误码。

## 验证路径与固定数据

公开 POST 会话 → 迁移 SQLite 身份 → POST turns → 原 JobRunner 双槽 Worker → 真实 build_agent → 供应商替身观察 system/tools/ToolMessage → 原检索及引用校验 → 持久消息和会话 GET → 浏览器展示与来源跳转。

复用 `test_shared_refs.seed_full_corpus`：机器学习导论、Agent 工程、数据库系统；论文精读、VAE 学习笔记、跨课程资料、已删除来源。知识检索用已有分片的“梯度下降通过反向传播迭代更新参数。”，另将网页条目归档、VAE 条目软删。没有扩大检索算法；无分片纯文本在 COURSE/ALL 不命中的原夹具不作为本票召回断言。

新增自动化仅覆盖身份、升级与重启、能力白名单、恶意工具调用、配置保留、范围检索和伪造 web 引用。其余复用现有聊天、恢复和预算用例。旧预算升级夹具同步 DROP 新列后再回放迁移，避免伪造的旧版本含未来列。

## 命令与结果

最终验收沿 `docs/agents/validation.md` 的统一入口顺序执行；原生退出码以各 `result.json` 为准。

| 层级 | 结果与范围 |
| --- | --- |
| API 身份红绿 | 新测试先因 `/api/agents` 404 失败，实施后 `test_chat_sessions.py` 13 通过，包括重启身份和公开未知身份拒绝 |
| 相关生产链诊断 | 独立入口/会话/streaming/context_budget/recovery/tool_budget 161 通过、4 个升级夹具重复列失败；修正夹具后该 4 项通过；这是直接运行的诊断证据 |
| 评审引用红绿 | 统一入口 `20261021T050612Z-d1f4941d/backend`：五档伪造 web 引用全部失败，确认问题；修正后结果见下方最终运行 |
| 最终针对性 | 统一入口 `20261021T050650Z-6bd69f1a/backend`：PASSED，33 通过，50.30 秒 |
| 完整前后端 | 统一入口 `20261021T050836Z-8b565539`：前端 PASSED，869/869、833.31 秒；后端 FAILED，1441 通过、1 项 sidecar 超时（pytest 1985.77 秒、运行器 1994.14 秒）。此前并行直接运行已中止，只保留诊断信息，不作为最终验收 |
| 基点对照 | 独立工作区同一统一入口 `20261021T055634Z-d9ab1020/backend`：FAILED，1 项失败、80.18 秒；同一测试同一行 `second.communicate(timeout=10)`，与全量失败形态一致 |
| 范围静态检查 | `pwsh -NoProfile -File scripts/check-changed.ps1 -Base 202a4c89267963d818cfc449dcb59931973404d9` 通过：触及文件 lint/格式、前端双类型检查及生产构建、后端 Pyright |
| 契约 | `pnpm --filter @knowrealm/api-types check` 通过 |
| 真实 HTTP/API/SQLite/Worker＋模型替身 | PASS，见下一节；只替换供应商，app/Worker/检索/引用/持久化真实 |
| 浏览器 | PASS：六主题 × zh/en × 1440/M、900/L 共 24 组，目录选择、身份、禁用说明、无横向溢出；另验证引用跳转、刷新/切范围、键盘和错误重试 |
| 真实模型 | NOT_RUN：本轮使用确定性供应商替身；默认用户目录未发现 provider 配置，未读取或改动其他用户数据目录 |
| Tauri/WebView2 | NOT_RUN |
| Windows 125%/150%/200% | NOT_RUN；浏览器 viewport/字号不是系统缩放 |

全量命令：`uv run --frozen --directory backend python -m scripts.run_tests all`。基点对照命令：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_server_process.py::test_second_sidecar_cannot_open_locked_data_directory`。二者顺序执行；基点为独立 worktree、独立 frozen 安装的前后端依赖，没有借用本轮环境。失败均在 `tests/test_server_process.py:497`，第二个进程 10 秒内未退出；未改变测试、扩大超时或跳过。此证据确认基点也存在该失败，整体全量状态仍为 FAILED，不宣称全绿。

标准结果保留在仓库根 `.pytest-tmp-runs/20261021T050836Z-8b565539/{frontend,backend}/`；基点 `tests.log`、`result.json` 复制至 `.scratch/multi-agent-refactor/.tmp/baseline-20261021T055634Z-d9ab1020/backend/`。截图及浏览器事实为 `.tmp/knowledge-course.png`、`menu-LIGHT_DEFAULT-en-narrow.png`、`menu-DARK_DEFAULT-en-narrow.png`、`citation-source.png`、`browser-results.json`、`browser-followup.json`；这些本机产物未入 Git。最终仅额外同步引用解析属性注释，Ruff/格式检查通过，没有更改已测行为。

## 真实 HTTP 链的可复查事实

隔离服务 `127.0.0.1:43136`，隔离前端 `127.0.0.1:1436`。Tauri IPC 使用官方 mock，业务 HTTP 均到真实 FastAPI。目录失败/重试场景额外替换 HTTP 失败响应，单独标记。

```text
session_id = 4a5b0ecd-daaa-47ce-81b4-fc5747cf873a
SELECT agent_id, mode, scope FROM chat_sessions WHERE id = <session_id>
=> knowledge, ASK, COURSE
turn_id = e4921b8e-73df-40aa-90ac-32b6ab642b67
turn.status = COMPLETED; execution.web_search = false
chat_model_requests(status, estimate.tool_count)
=> COMPLETED/1, COMPLETED/1
request_id = 981e0c07-ba46-47f5-9b0b-6450b8eb8594
request_id = e1fcb2e7-bc9a-40bc-b109-3afda777adaf
usage_json = NULL（供应商替身没有真实用量，不记为 0）
chat_context_inputs.system 含“你是 KnowRealm 本地知识助手。”
不含 plan_batch_operations / propose_ingest 指引
answer_id = 0fead858-1f9c-4ed7-8b0b-6184b92ec2f3
citation = record d0000000-0000-4000-8000-000000000011
quote = 梯度下降通过反向传播迭代更新参数。
agent_proposals / agent_operations / agent_runs = 0 / 0 / 0
切换全部资料后 session_id = 45756585-0bc2-48b3-8a8e-fd3f86996910
新会话 GET agent_id = knowledge
```

模型实际观察（自动化供应商接缝）：四档非 FREE 的每次 bind_tools 均为 `[search_library]`；FREE 无工具定义，完整请求估算为 0 个工具。恶意调用收到 error ToolMessage，公开预估与真实模型请求记录的 tool_count 均符合 0/1 白名单。

引用点击到 `/records/<id>?tab=transcript&highlight=...`，原句可见；刷新后原会话仍为 knowledge。键盘 Enter 打开菜单、Home/方向键定位、Space 选择 knowledge、Escape 关闭并还原触发器焦点。目录错误提示出现后重试恢复真实两项目录。浏览器无 pageerror。

视觉采用既有 DESIGN 令牌和控件；按 Raskin 模式安全原则常显身份，侧栏允许身份换行；没有增加独立视觉系统。`lint_slop.py` 对三个组件的 focus/hover 报告来自只扫描调用文件的静态限制：实际焦点/悬浮由 Button、buttonVariants 和 DropdownMenu 原语提供，浏览器键盘与截图已核对，不重复添加 CSS。

## 双轴评审

### Standards

首轮：生产代码无明确规范违规；指出最终验收须使用统一运行器，以及一条在调用被测函数前已抛出的重复测试断言。已移除该无效断言并纠正验收流程；独立评审复查无遗留规范问题。

### Spec

首轮：发现 knowledge 的通用解析器可能把模型编造的网站投影为正式 web 来源。已补五范围生产 Worker 回归并修正输出边界；独立评审复查无遗留规格问题。其余身份、能力、配置和创建路径无新增发现。

## 本地 URL 引用评审修复（2026-10-21）

- 修复 knowledge 将含 URL 的合法本地摘录先解析为 web、再误删的问题。两个解析器增加默认开启的 `allow_web` 参数，Worker 按固定 Agent 身份关闭 knowledge 的 web 分流，移除事后过滤；沿用本地原文校验和来源归属，不增加模型调用或改变通用助手行为。
- 新增一个参数化 Worker 回归，共 7 项：RECORD/COURSE/ALL/LIBRARY_ITEM 的记录原文，以及 COURSE/ALL/LIBRARY_ITEM 的资料直挂正文。公开 API → 真实 SQLite/Worker → 引用解析 → 持久消息 GET；供应商为模型替身，输出同时包含合法本地 URL 摘录和伪造网络引用，断言只保留正确来源 ID 与原句。本用例验证输出校验，不声称模型实际调用了检索工具。
- 红灯：统一入口 `20261021T074704Z-41215fb2/backend`，7 项均因引用列表为空失败。修复后执行 `uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_independent_agents.py tests/test_chat_streaming.py tests/test_library_retrieval.py tests/test_shared_refs.py`，`20261021T074809Z-208a8c9b/backend` 135 项通过，包含原伪造引用防线和通用助手网络/混合引用回归。
- `pwsh -NoProfile -File scripts/check-changed.ps1` 通过，触及文件 Ruff/格式/Pyright 均通过；未重跑全量、真实模型或原生桌面，原有未验收项保持不变。日志与临时数据库未 add/commit。

## 可重复桌面步骤与资源

1. 独立 data-dir 准备课程 A/B 及各自标记资料，再准备归档、软删和跨课资料。
2. 新建菜单选择本地知识助手、课程 A；提问标记内容，并尝试要求建课/联网。观察仅合法本地来源，业务无新增。
3. 点击引用核对原文；刷新和进程重启检查身份；切换范围检查新对话继续为 knowledge；FREE 说明缺少挂载范围。
4. 新建 general，复查既有确认卡和原课程/资料 CTA；六主题、中英、大字号和窄窗复查选择/禁用/错误状态。
5. 真实模型、Tauri/WebView2 和 Windows 各系统缩放分别记录；未执行保持 NOT_RUN，工具未实际触发保持 NOT_TRIGGERED。

隔离 HTTP/Vite 服务已停止，43136/1436 无监听；用户原服务不动。自动审批拒绝删除本票临时测试目录和隔离数据库，返回 `blocked by policy`，因此这些产物及临时脚本保留在忽略目录，均未 add/commit。基点 worktree 已从 Git 注册移除，但 `git worktree remove --force` 报 `Directory not empty`，同名目录仍有残留；不声称清理完成，不改用其他途径绕过删除拒绝。标准运行器记录、基点结果副本和浏览器截图保留供复查；用户原有 worktree 未修改。
