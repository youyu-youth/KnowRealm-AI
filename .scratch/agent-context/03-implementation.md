# 工单 03：受限原文取回实施记录

实施基点：`8374992282d7513548c7f276ae3f66aa57235baf`，当前分支 `feat/extend-dev-09`。实现完成，工单转 `ready-for-human`；真实模型与桌面验收仍待完成。用户已有 `.scratch/agent-context/baseline/` 未修改。

## 实现范围

- `search_context` / `read_context` 为只读 Tool，所有会话范围可用；与独立来源页 API 共用 Service。历史和快照限定当前会话、当前段、轮次及来源身份，资料沿用领域检索的 RECORD/LIBRARY_ITEM/COURSE/ALL 和共享引用规则。
- 搜索返回真实摘录、位置、来源版本；读取默认最多 2400 字，支持稳定游标与剩余量。版本、摘录位置、会话段或共享关系失效时明确拒绝。重复正文的分片身份及时间/页码按顺序定位，消息深处命中可直接定位。
- 小材料可容纳时仍用全文；完整请求有预算压力时，挂载 Record 和 Library Item 改取相关片段，优先保留历史承接，不以无关材料填窗口。
- 迁移 `0048` 仅 DDL，增加 SQLite 受控输出表。不可重建大正文按 turn/namespace/logical-call 保存，恢复校验工具与参数指纹；网页搜索在原 400 字裁剪前保存完整返回，恢复复用原内联结果。领域可重建结果和业务回执不改写、不伪造旧正文。
- 模型投影按需改为有效 JSON 来源指针；原 ToolMessage、业务结果和已落库字符消费保持。两 Tool 共享现有 6 次及输出字符预算，每次模型请求仍执行完整预算检查；页面普通读取不扣工具次数。
- 独立上下文页增加“来源原文”，摘要来源可进入定位；支持搜索、继续、重新读取、未就绪和失效反馈，双语及四主题沿用现有组件和语义令牌。没有引入依赖、文件服务、任意文件/Shell/SQL 权限。
- 图版本升 `v4`，普通/研究 prompt 升 `v27/v28`；契约生成、错误登记和双语同步。04 的固定上下文和 05 的排除/旧段纳入未实施，02 已登记的其他边界未随本票关闭。

## 完成证据

`backend/tests/test_context_retrieval.py` 使用真实迁移、文件 SQLite、API、Worker 和生产 `build_agent`，模型及网络为替身：

1. `test_compacted_source_is_read_through_real_framework_tool`：已压缩历史的来源经实际 `read_context` Tool 回到后续模型输入，验证被摘要省略的原句。
2. `test_large_output_projection_preserves_snapshot_and_is_readable`：大 JSON 保存完整快照，模型拿有效指针，实际 Tool 分段取回；原正文、回执和消费不被改写。
3. `test_real_web_tool_keeps_pre_truncation_text_readable`：真实 `web_search` 调用生产裁剪及快照路径，网络替身返回长正文；原内联仍裁剪，尾部详情经受控 API 可取回。
4. `test_output_and_cursor_survive_worker_restart_without_reexecution`：Worker 重启后同逻辑调用复用结果、继续游标可用，不重复执行。已有活跃引用不会因终态提前清理，会话失效后拒绝读取。
5. 跨会话/段、追加历史后的继续、非法游标、版本变化、共享移除/归档、次数与字符耗尽、完整输入阻断、旧工具配对、深处摘录及重复分片定位由同文件和原预算/资料回归覆盖。旧请求未保存正文时返回不可用，不能从摘要编造。

## 验证结果

- 相关组合回归：115 项通过（`03-verified-regression.log`），覆盖原文取回、网页、完整输入、工具预算、摘要、资料/共享引用及错误码。最后统一分片定位后，`uv run --directory backend pytest --basetemp=.pytest-tmp-retrieval-03-locator -q tests/test_context_retrieval.py`：7 项通过。
- 前端相关：`pnpm --dir apps/desktop test -- --maxWorkers=1 src/pages/chat.test.tsx src/features/chat/ContextCompactionList.test.tsx src/features/chat/toolIcons.test.ts`：48 项通过。双语一致性：3 项通过。
- 触及范围门禁：`pwsh -NoProfile -File scripts/check-changed.ps1 -Base 8374992282d7513548c7f276ae3f66aa57235baf` 全部通过（`03-final-gates.log`）：ESLint、Prettier、两份 TypeScript 检查及 Vite 构建、Ruff/格式、Pyright 0 错误。API `pnpm --filter @knowrealm/api-types check` 已通过，生成物包含 quote/offset 和分页契约。
- SDK 预算回归因新增两个 Tool 的实际 schema 成本重新校准部分测试窗口至 45000；保留重试次数、恢复身份和最终输入断言，没有扩大等待超时。旧迁移回退测试同步删除新表后再回放迁移。
- 两轴 code-review 审查已完成：发现的 Library Item 选材、深处/重复摘录定位及重复分片元数据问题均修复，最后只读复核没有剩余阻塞项。
- 浏览器使用真实页面组件及 API/Tauri 替身，检查四主题、英文、宽窗和 900×700 窄窗、18px 字号、键盘焦点、继续按钮及局部滚动，无横向溢出。仅为浏览器模拟，DPR 不等于 Windows 系统缩放。

## 全量边界

- 前端全量一次：`pnpm --dir apps/desktop test -- --maxWorkers=4`，724 通过、9 失败（`03-frontend-full.log`）。独立 detached 基点、独立 frozen 依赖重跑相关 7 文件：81 通过、6 失败（`03-frontend-baseline.log`），稳定复现 CourseBrainReview、LearningPlanTab 三项、RecordDetail 与 CommandPalette；这些文件未修改。
- 其余 Settings/TodoPanel/TodayStatsBand 超时或交互失败在当前单 worker 重跑为 46 通过、2 失败，TodayStatsBand 通过。随后相同窄范围对比中，Settings 的 15 秒超时在基点也复现；TodoPanel 当前组合测试失败，但当前单独执行该用例通过（`03-todo-isolated.log`），基点同用例通过。后两项按并发/执行顺序敏感记录，没有把整套测试改成绿色。没有按历史名单跳过全量，也未修改无关模块或测试超时。
- 后端全量一次：`uv run --directory backend pytest --basetemp=.pytest-tmp-retrieval-03-all -q`。日志停于约 29%，已出现一个失败但未输出终结摘要，长时间停滞后终止本次专用进程（`03-backend-full.log`）。不能声称全量通过或确认该失败归因。最后活动用例 `test_all_session_fts_library_hits_and_web_guidance` 当前单跑通过（17.76 秒），独立基点对比见补记。
- 基点 worktree 为本次新建 `E:/workspace/project/my/KnowRealm-AI-context03-baseline-8374992`，独立安装 `pnpm install --frozen-lockfile` / `uv sync --frozen --directory backend`；uv 首次网络下载失败，重试安装成功。不借当前工作区依赖冒充基点。
- 基点执行 `uv run --directory backend pytest --basetemp=.pytest-tmp-context03-baseline -q tests/test_chat_streaming.py tests/test_conversation_compaction.py`：110 通过、3 失败（`03-backend-baseline.log`）。失败为 `test_long_mounted_stream_reads_confirmed_assets_and_valid_citations`、`test_context_contains_system_snapshot_and_last_ten_turns`、`test_response_process_separates_commentary_and_all_parallel_tools`。当前三项窄范围也失败（`03-backend-known-failures.log`）：分别为错误码旧断言、十轮裁剪旧断言、工具回执成功断言，形态与基点一致。基点挂起用例通过，不能据此确认全量停滞原因。

## 尚未验证

真实模型的检索质量、真实网页网络、供应商实际用量与成本、真实 Tauri/WebView2 和 Windows 系统缩放均未验证。没有将替身或浏览器证据代勾真机验收，后续工单保持未完成。

## 临时资源

自动审批审查拒绝本次临时资源清理命令，返回 `blocked by policy`，命令未执行。新建基点 worktree、`backend/.pytest-tmp-retrieval-03*` 和 `.scratch/agent-context/03-preview.html` 保留，不换删除方式绕过拒绝；这些资源不纳入提交。用户原有基点 worktree 保持。
