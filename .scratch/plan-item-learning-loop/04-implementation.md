# 04 实施与验收

基点：`9fcc7279ffb0635cd77a50a4149062895b7afe8a`，开始时工作区干净。

## 实施范围及验证接缝

- 已阅读 03 的 `ab1758e`、`52e951f`、`9fcc727` 历史与实施/评审记录。复用固定题面、QuizTest 作答评分、PRACTICE_PREPARE Worker、受控 Operation；不另建评分引擎或队列。
- 检查点一：真实 HTTP 确认要求/准备/建卷/作答/交卷 → 生产评分 Worker → 逐题错误与部分分数 → HTTP/Agent 定向重试 → SQLite 核对成功题、答案、学习事件及任务身份。固定 15 道简答题，外部评分替身产生单题无效输出、整体异常及等待窗口。
- 检查点二：同一真实入口在 6/15 时准备重练 → 不足/取消/基线变化保留旧答案 → 成功事务放弃旧轮并建新轮 → 历史与最近轮次查询。固定 15/30 道相关题及无关题；外部匹配替身只替换模型推理，不替换候选筛选、事务、Worker 或迁移。
- 页面通过 MSW/DOM 验证分母、部分成绩、重试错误/刷新、确认取消、历史切换及只读边界；这些不代表原生桌面验收。
- 修改范围：计划练习领域/HTTP/Schema、QuizTest 计划分支、评分执行身份校验、Agent Tool/Operation/确认卡、页面/查询缓存、契约生成及双语。只新增本票行为的验收，不补历史覆盖率。
- 真实模型、Tauri/WebView2、屏幕阅读器、Windows 系统缩放：NOT_RUN，归 05。临时测试日志/数据库不提交。

## 验证结果

- PASS：本票相关后端 81 项在全量中全部通过：`test_practice_preparation.py` 25、`test_practice_round.py` 23、`test_practice_recovery.py` 15、`test_quiz_tests.py` 18。新恢复/重练覆盖 14/15 的单题重试及事件增量、零已评分/模型超时、并发重试同任务与应用重启重放、6/15 明确确认、未用题优先/复用、并发建轮及第二请求改参数冲突、准备失败/取消/进度/要求/来源变化保留旧轮、旧轮晚到评分、已完成项首次完成时间及真实 Agent 提案执行。证据：`.pytest-tmp-runs/20261018T034649Z-8d0161cc/backend/`。
- PASS：真实在途恢复快照。生产 Worker 已落 14 题，第 15 题模型替身等待时通过 SQLite backup 取得真实 RUNNING 快照，另一隔离数据目录经生产 lifespan 恢复为 GRADING_FAILED / WORKER_INTERRUPTED，14 题结果与部分成绩保留，重试只调用 1 题。未伪造 job 或评分终态。独立证据：`.pytest-tmp-runs/20261018T033019Z-85a4a2ab/backend/`；亦包含在上述 15 项。7 个真实测试数据库（含恢复副本）的对象/要求/轮次/请求/任务/覆盖量/事件去重核对另存 `.pytest-tmp-runs/20261018T034649Z-8d0161cc/practice-facts.json`，不含答案或密钥。
- PASS：最终相关前端 91 项（计划准备/历史/重试、卷面结果、聊天确认卡、双语），证据：`.pytest-tmp-runs/20261018T044405Z-cd524a57/frontend/`。该定向运行包含全量结束后的轮次 URL 往返、评分错误翻译及已交卷重练提示，不能冒用此前全量的覆盖范围。
- 相关后端批跑 77 PASS / 4 FAIL，发现新增可选 `abandon_confirmed` 经既有宽松 Tool schema 传入 None，使旧首次准备调用被判缺参。已仅在该 Tool 入口移除缺省 None，由业务 Schema 取 False；不放宽确认校验。原 4 项用例重新执行全部 PASS：`.pytest-tmp-runs/20261018T034454Z-b87775ba/backend/`。失败证据保留：`.pytest-tmp-runs/20261018T033445Z-45a7f0b3/backend/`。
- PASS：最终 `pwsh -NoProfile -File scripts/check-changed.ps1`（范围 ESLint/Prettier、两份 TypeScript、Vite 构建、Ruff lint/format、范围 Pyright 0 错 0 警告），日志 `.pytest-tmp-runs/practice04-final-check.log`；`pnpm --filter @knowrealm/api-types check`，`git diff --check`。构建保留既有路由测试文件/大包警告，不宣称零警告。
- 双轴静态评审初评共 4 项均修复，两轴复核各 0 遗留，见 [04-review.md](./04-review.md)。
- 前后端全量：入口 `uv run --frozen --directory backend python -m scripts.run_tests all`。前端 832 PASS / 6 FAIL，后端 1382 PASS / 33 FAIL；均为 FAILED，记录 `.pytest-tmp-runs/20261018T034649Z-8d0161cc/{frontend,backend}/`。后端新增迁移影响的 4 个旧版本回退夹具、遗漏新增评分工具的 1 个挂载矩阵已精准同步，分别复跑 4 PASS、1 PASS：`.pytest-tmp-runs/20261018T044324Z-66e13b8b/backend/`、`.pytest-tmp-runs/20261018T044842Z-217b46f1/backend/`。未重跑第二次全量，不把这些定向通过改写成整套全绿。
- 前端 6 个失败在独立 03 基点全部复现：RecordDetail 1、CommandPalette 1、LearningPlanTab 3、toolIcons 1；筛选 4 文件结果 27 PASS / 6 FAIL，失败用例和断言形态一致。基点命令由同一 `scripts.run_tests frontend` 入口调用上述 4 文件，完整命令/独立路径/干净源码标记见 `.pytest-tmp-runs/baseline-practice04/20261018T044910Z-83021f3e/frontend/result.json`。
- 后端基点对全量失败中除已修复回退夹具外的 29 个 node ID，使用相同 `scripts.run_tests backend` 入口、独立迁移数据及冻结依赖复测，得到 28 FAIL / 1 PASS；唯一通过为本票已同步的工具挂载矩阵。其余 28 个失败与当前全量集合完全一致：旧迁移 1、聊天 2、context_pins 3、context_rules 2、conversation_compaction 18、document_import 日志 1、quizzes 设置响应 1。错误均为同类迁移/断言/等待失败；document_import 两侧均断言日志不得包含 `private-source-path`，栈中的 worktree 路径不同，不能逐字等同。基点记录 `.pytest-tmp-runs/baseline-practice04/20261018T045059Z-36f04135/backend/`，逐用例比较另存 `backend-comparison.json`。未修改这些历史失败，也未过滤全量或延长等待来取得绿灯。

## 实现与界面取舍

- 迁移 0055 只新增 DDL：试卷绑定准备身份的可空列/唯一索引、启动请求映射、评分请求映射。已有 03 轮次保持原固定内容，不猜测回填历史请求参数。普通 MOCK/ADAPTIVE 保留原判分和重考语义。
- 评分状态、完整性和成绩分开；成绩从本轮已评分题计算，零已评分为 null。失败保留逐题错误与任务错误，成功题结果及学习事实不重置。重试请求（包括并发别名）绑定原任务，用户答案及当轮固定判分依据不变。
- 重练准备保存旧轮身份、进度指纹、要求修订及确认事实；Worker 和提交处重验。只在足量且去重的新题集通过校验后原子切轮。已交卷旧轮继续评分，按启动轮序查询默认结果；人工完成仍复用已有入口。
- Agent 复用 `prepare_plan_practice` / `start_plan_practice` 和新增 `retry_plan_practice_grading`。未交卷放弃影响在自动授权档也须人工确认，执行端校验提案事实；评分重试遵循既有 L1 授权及回执。只读状态禁止新用户操作，已受理评分允许实际后台收尾。
- 历史选择进入 URL，服务端状态由 Query 读取；开始/重试精确失效轮次详情和计划练习查询。旧轮题面、要求及已答内容可查，ABANDONED 仍不揭示未交卷参考答案。
- 界面沿用 DESIGN.md 的语义色、字号与公共组件，仅“开始新轮”使用高对比主按钮；重练、继续及历史入口为次要操作。确认弹窗展示已答数量与放弃条件，允许取消。未引入新样式令牌/动画/状态仓库。
- 确认卡重试使用“仅补齐未评分题”专用说明；已交卷旧轮显示保留结果的说明，未交卷重练则展示已答进度与放弃影响。相关双语文案及组件断言已在最终 91 项中通过。错误码清单仅同步已批准行为的使用模块/说明，未新增错误码或架构规范。
- `lint_slop.py` 对三个组件报 3 severe（缺 focus）和 3 hover warning；这是不追踪共享 `Button`/`buttonVariants` 的静态误报。已核对 `components/ui/button.tsx:7` 提供 focus-visible border/ring，`:11-20` 各变体提供 hover；组件均复用这些样式，不添加重复局部样式来迎合脚本。此人工核对不代替原生键盘验收。

## 桌面复验与未执行范围

NOT_RUN：真实匹配/评分供应商质量与用量、Tauri/WebView2、屏幕阅读器、Windows 125%/150% 系统缩放；集中在 05 验证，不代勾。以上 HTTP 使用 ASGITransport、生产路由/迁移/SQLite/Worker，模型为外部替身；前端为 DOM/MSW/Router 集成，不代表真实网络进程或原生桌面。

使用隔离数据目录，准备至少 30 道相关且不同的题及少量无关题：

1. 确认 15 道题要求并开始，答到 6/15。触发重练后取消确认，再模拟匹配失败，旧轮始终可继续且答案不变；准备成功后才“开始新轮”，旧轮转已放弃但卷面/答案可查，当前可作答轮恰好一轮。
2. 检查新题优先及不足时复用数量提示，不自动扩源。修改要求后确认，当前轮仍显示原修订/主题/数量/题型/来源，下一轮才使用新要求。
3. 简答交卷后形成 13/15 已评分，观察部分分数与实际分母、逐题错误；重复重试并离开返回，成功题与答案不变，缺口填满后显示完整结果。零已评分应无成绩。
4. 用户确认完成后再重练；检查完成时间、完成数量和估时不变。延迟旧轮评分，默认仍展示最近启动轮；切换历史及刷新/返回后轮次不混淆。
5. 历史计划、完结目标、跳过项只读；已受理评分仍允许后台收尾。四主题、窄窗/字号、Tab/Enter/Esc 与屏幕阅读器分别记录。

清理：测试数据库在 runner 独立 basetemp，日志在 `.pytest-tmp-runs/`；均未 add/commit。不启动或改写用户真实数据目录，不修改供应商实际配置。若为全量失败建立基点 worktree，路径与清理结果另列。

基点环境：`E:/workspace/project/my/KnowRealm-AI-baseline-practice04`，detached `9fcc727`，使用 `uv sync --frozen --directory backend` 与 `pnpm install --frozen-lockfile` 安装独立 `.venv`/`node_modules`；安装和复测与当前全量顺序执行。两次基点测试启动时均为干净源码（见 result.json）。前端仅产生路由生成文件的行尾噪声，已恢复后再启动后端；未复制当前源码或借用当前依赖。两套原始日志/result.json 已复制到当前工作区忽略目录。

清理状态：BLOCKED_BY_POLICY。已核对绝对路径、2392 个 reparse point 及其目标全部处于该专用基点目录内（外部目标 0），且两套测试进程均已退出；随后执行“先用 PowerShell Remove-Item 移除链接本身，再 git worktree remove --force 该基点”的命令，在进程创建前被工具执行策略拒绝，原文仅为 `rejected: blocked by policy`。未换删除方式或重试绕过。上述基点目录、独立依赖、测试数据和 worktree 登记仍残留，不能宣称临时资源已清理；未动用户其他 worktree。
