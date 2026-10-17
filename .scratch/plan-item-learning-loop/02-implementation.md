# 02 实施与验收

基点：`77e4585efea22db5523814c056ffcd626cb1cacb`，当前分支 `feat/extend-dev-09`。本票实现范围为要求确认、持久题集准备与确认补源；实际答题属于 03，真实语义质量和原生桌面验收属于 05。

## 已实现入口与边界

- 课程学习计划的练习项可进入独立准备页，首次题量留空，合并确认主题、正整数量、五题型及真实资料对象。刷新、离开再进入均查询持久状态；编辑时刷新保留输入，失效来源可取消选择。
- HTTP：`GET /api/plan-items/{id}/practice`、`PUT .../requirements`、`POST .../preparations`、`POST .../preparations/{preparation_id}/cancel`，复用启动令牌鉴权、领域事务与 ProcessingJob/JobRunner。
- Agent：已装配 `get_plan_practice`、`confirm_practice_requirements`、`prepare_plan_practice`、`cancel_practice_preparation`。缺少明确数量或来源时应先追问；要求及扩源确认在三档授权下均强制业务确认卡，再由原受控操作路径执行。页面上下文、自动执行权限不替代确认事实。
- 只从本课程归属、有效资料中的 ACTIVE 已采纳原题取候选，确定性过滤题型、越界与规范化重复副本。模型只判定真实候选身份及相关类别，不生成题，不读取用户答案；优先匹配确认范围，足量后停止，缺题才检查其他归属资料以形成建议。
- READY 必须恰好 N 道确定相关且不同的题；不确定判定、扫描预算未完为 INCOMPLETE；完整检查且没有不确定项才可报告 INSUFFICIENT。未确认来源只形成建议，不能入选。
- 公共投影只含要求、任务状态、目标/合格/实际检索数量、资料和结构化匹配依据，不提供题干、选项、参考答案。内部保留要求修订、计划正文基线、选中原题、匹配类别及原题/来源版本散列，03 建卷提交时仍须重验。
- 来源/题目变化在受理事务及 Worker 执行校验中与已确认版本基线比对；旧要求、取消、权限降级在最终写事务和独立计量事务重验。LLM 平台复用供应商、外发同意、预算与 LlmCallLog，不另建旁路调度或计费。

## 固定验证路径

真实 HTTP PUT 要求 → 学习计划领域校验及 SQLite 追加修订 → POST 准备并同事务持久化 ProcessingJob → lifespan 注册的 JobRunner 领取 → 确定性范围、题型与副本过滤 → 外部推理边界 → 身份及版本重验 → GET 页面及已装配 Tool 的无答案投影。

固定数据：本课程来源一 8 道、来源二 7 道 Redis 简答题，另放无关主题、重复副本、其他课程、共享引用、未采纳及已删除干扰题。先仅确认来源一，取得 8/15 缺口与来源二建议；拒绝不改变要求，再确认两个来源的新修订，必须恰好 15 道。

替身只替换外部模型生成，不替换 Service、迁移、HTTP、事务或生产 Worker。额外验证伪造/重复/遗漏候选身份、题型、过期修订、来源变动、取消、降权、重放、模型失败及重启对账。前端在现有 MSW 接缝验证合并确认与等待恢复。通过条件包括无答案外泄、无随机降量、未完整检索不冒称课程不足。

原始数据库、测试日志与临时截图不提交。原生桌面及真实语义相关性留待 05，以下分层记录仅按实际证据更新。

## 验证证据

- TDD RED：新增要求查询入口测试得到 404，运行记录 `.pytest-tmp-runs/20261017T031505Z-ccf1bf29/backend/result.json`。
- 首条要求保存路径 GREEN：`.pytest-tmp-runs/20261017T031847Z-0967d3e4/backend/result.json`。
- 真实 HTTP/SQLite/Worker 定向回归曾发现任务终态与旧结果被分次读取的竞态，已改为同一 SELECT 投影；后续 17 项及 18 项准备测试通过。最终完整测试及补验结果见下方记录。
- 双轴只读评审均通过，初评各 3 项 P2 全部修复，未解决项各 0，见 [评审记录](./02-review.md)。
- 浏览器：隔离真实 API/SQLite/生产 Worker + 可控外部模型，Tauri IPC 用官方 mockIPC 替身。zh/en × 四主题 × 1440/16px、1099/18px、800/20px 共 24 组通过；完整走通 8/15 缺口→保留输入→确认补充 7 题→重载恢复→恰好 15 题。检查页面错误、横向溢出、匹配依据、键盘与减少动态效果。证据 `.pytest-tmp-runs/practice-browser-20261017/browser-result.json` 和同目录 `01-*.png` 至 `04-*.png`。已目视核对亮色宽屏及英文暗色窄屏。
- UI 扫描器将项目 Button/Checkbox/Input 封装外的焦点样式报为缺失；现有公共组件已有 focus-visible，未重复添加样式掩盖扫描器局限。自动扫描不代表屏幕阅读器或原生验收。
- 真实模型、Tauri/WebView2 与 Windows 系统缩放：NOT_RUN。

静态检查记录位于 `.pytest-tmp-runs/practice-browser-20261017/`：

- `build-final.log`：`pnpm build` 通过（含两份 TypeScript 配置）；既有大包提示保留。
- `static-final.log`：改动 Python 的 Ruff check/format、改动前端文件的 Prettier 均通过；`scoped-final.log`：除基点已有警告的 LearningPlanTab 外，本票 TS/TSX ESLint 通过，13 个改动 Python 文件 Pyright 为 0 错误。
- `check-changed-final.log`：标准入口失败，仅 LearningPlanTab 导出的旧 `toastMutationError` 触发 `react-refresh/only-export-components`（现 773 行，基点 760 行）。独立基点相同命令也失败，见 `baseline-eslint.log`；没有放宽规则。
- `pyright-final.log`：全库 6 个错误均在未改的 `test_chat_turns.py`（5 个未使用变量）及 `test_error_code_guard.py`（1 个 unknown 类型）。独立基点同文件复现相同 6 个错误，见 `baseline-pyright.log`。
- OpenAPI 导出与生成类型检查通过，生成文件已同步；错误码三方登记由现有后端防线验收。

完整运行 `uv run --frozen --directory backend python -m scripts.run_tests all`，证据 `.pytest-tmp-runs/20261017T034127Z-2e41fbbc/{frontend,backend}/`：前端 803 通过 / 7 失败，后端 1329 通过 / 31 失败；本票后端 22 项全部通过。全量启动后补上的焦点恢复改动已单独启动新进程复验，前端练习页 5 项全部通过，记录 `.pytest-tmp-runs/20261017T043153Z-0ac13327/frontend/`。原始全量失败保留，没有写成全绿。

独立 detached 基点 worktree 固定在上述提交，自行执行 `pnpm install --frozen-lockfile` 与 `uv sync --frozen --directory backend`，没有复用当前工作区依赖。以相同测试入口复测失败节点及前端四个失败文件：

- 后端原 31 个失败节点在基点为 26 失败 / 5 通过，记录 `practice-browser-20261017/baseline-backend/`。26 个相同失败涉及旧迁移回拨、旧聊天断言、压缩/恢复预算夹具、文档错误日志及习题偏好，保持未修改；压缩失败基点同样存在，没有为本票放宽生产预算。
- 前端基点 27 通过 / 6 失败，记录 `practice-browser-20261017/baseline-frontend/`；6 个相同失败为 RecordDetail 1、CommandPalette 1、LearningPlanTab 3、toolIcons 唯一性 1。
- 本票同步现有夹具：工具装配矩阵的七种场景精确名单加入四个练习工具；旧库回拨 0044 前按依赖顺序清除 0052 两张新表。定向命令 `uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_chat_streaming.py::test_scope_mounting_matrix_tool_visibility tests/test_tool_budget.py::test_legacy_nonterminal_turn_requires_stop_and_new_question` 为 5 通过，记录 `.pytest-tmp-runs/20261017T044157Z-4afb34a0/backend/`；两文件 Ruff/format/Pyright 也通过，见 `fixture-pyright.log`。没有削弱断言、修改旧迁移或扩大历史修复。

上述 `practice-browser-20261017/...` 均相对 `.pytest-tmp-runs/`。首次交付时本票后端 22、前端 5、关联夹具补验 5 均通过；全量原始失败与 32 个基点复现的历史失败明确分开，未重复全量，也未把补验换算成新的全量通过数。

## 来源确认版本的后续复核修复（2026-10-17）

- 缺口真实存在：确认后修改资料更新时间或题干，准备接口仍返回 202；已受理但执行前修改题干，Worker 也会成功。原 writeback 仅对照执行开始时的版本，不能代替确认时的来源基线。RED 证据分别为 `.pytest-tmp-runs/20261017T050416Z-43f56477/backend/`（2 项）及 `.pytest-tmp-runs/20261017T050456Z-2a5c9278/backend/`（1 项）。
- 复用已有 `source_versions` 与 `PRACTICE_SOURCE_INVALID`，领域服务统一校验已确认的归属、有效性和版本。受理在既有写锁/事务内校验后才创建任务；Worker 的执行及提交/计量校验也使用同一确认基线，覆盖排队期间漂移，模型调用前即拒绝。页面与 Agent 共用 `prepare`，不增加旁路入口、迁移或 HTTP 契约。
- 新增 3 项回归验证受理拒绝且无准备记录/任务/计量、要求保留、重新确认后同一未受理请求可重试，以及排队漂移时零模型外发、旧请求重放返回原任务。完整 `tests/test_practice_preparation.py` 为 25 项通过，证据 `.pytest-tmp-runs/20261017T050524Z-9dad8fb1/backend/`；`pwsh -NoProfile -File scripts/check-changed.ps1` 的 Ruff、格式及 Pyright 均通过。此次仅后端小范围修复，未重跑全库、真实模型或原生桌面验收。

## 前端组件复核（2026-10-17）

结果来源与补源建议的两段同形渲染已合并为 Feature 内的 `PracticeSourceList`；Page 中仅展示确认资料名称的列表保持其独立语义。要求表单原样移至 `PracticeRequirementsForm`，保留 `item_id` key、草稿基线、刷新保留输入和保存后焦点；Page 从 359 行缩为 163 行。规范的约 150 行阈值针对单组件 JSX，当前 Page/Form 主 JSX 返回段分别为 93/139 行，无需为文件总行数继续拆分。

复用原有页面测试，仅在缺题补源用例补充两类来源匹配依据的可见断言；5 项全过，证据 `.pytest-tmp-runs/20261017T051204Z-765fbf58/frontend/`。`scripts/check-changed.ps1` 的 ESLint、Prettier、两份 TS 检查及 Vite 构建全部通过。UI 扫描仍把使用公共 Button/Checkbox/Input 的三个文件报为缺少局部 focus/hover，已核对公共组件继承样式并保留焦点测试，不重复添加 CSS；未重跑完整浏览器矩阵或原生桌面验收。

## 临时资源与数据

浏览器独立服务端口 43179/1438 已停止，浏览器已关闭。测试数据库、模型替身、Playwright 脚本、日志及截图均留在被忽略的 `.pytest-tmp-runs/`，不加入提交；没有操作用户生产数据。验证中曾使用独立基点 worktree 和各自安装的依赖以复核历史失败。

基点证据已复制回上述忽略目录。`git worktree remove` 因测试生成文件的行尾状态拒绝；确认无内容差异后 `--force` 清理仍报 Directory not empty，保留残余 `E:/workspace/project/my/KnowRealm-AI-baseline-practice-02`。后续原生 PowerShell 递归清理被自动审批以 `blocked by policy` 拒绝，未再尝试删除。此残留不加入当前分支提交，不影响验证数据及生产数据。

## 05 的真实边界复验入口（尚未执行）

1. 使用单独数据目录启动真实 Tauri/WebView2，配置实际供应商并开启明确的外发同意；准备一门课程，两份归属资料各含 8/7 道已采纳 Redis 题，另置无关、重复及越界干扰。记录应用版本、Windows 缩放、主题、供应商及课程/资料/计划项 ID。
2. 从计划项进入准备页，核对题量没有预填；输入 15、核对主题和题型、只选第一份资料并确认。分别记录 HTTP 受理、执行中、完成的任务 ID/状态和要求修订，确认缺口与真实扫描范围、没有答案外泄。
3. 先不批准补源并刷新，要求不得变化；随后核对第二份资料并确认新修订，再准备得到恰好 15 道。核对来源依据、重复排除及真实模型相关性，不能把判定不确定当确定不足。
4. 分别覆盖取消、供应商失败、修改要求、资料变化和重启：旧要求保留，过期结果不能提交，显式重试有新任务，重放同一请求不重复受理。Agent 在三档授权下均须核对业务确认卡；降权后不得提交旧操作。
5. 在四主题、窄窗口、Windows 100%/125%/150% 缩放下检查滚动、文本、Tab 焦点及屏幕阅读器；此步骤不能由浏览器 DPR 代替。结束后关闭测试进程，恢复原供应商/同意设置，移除仅本次创建的测试目录，保留脱敏验收记录。

## 恢复设计

同一请求 UUID 重放返回同一任务，不重复匹配或计量；同 UUID 改参数拒绝。进程中断时外部供应商是否已计费无法确定，RUNNING 对账为可显式重试的 WORKER_INTERRUPTED，不自动再次外发；已确认要求保留。PENDING 正常接续。匹配每次最多 20 批、每批 30 个候选，达到调用预算仍不足时为 INCOMPLETE，明确实际扫描量，不宣称全课程不足。
