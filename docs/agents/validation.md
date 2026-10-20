# 验证与基点复测

需要按改动范围检查、比较历史失败、建立隔离 worktree 或记录验收结果时阅读本文。工具版本及具体命令以仓库配置和 CI 为准。

## 改动范围检查

在仓库根或任意子目录调用 PowerShell 7 脚本；路径按仓库根解释，不按调用者当前目录解释：

```powershell
pwsh -NoProfile -File scripts/check-changed.ps1 -ListOnly
pwsh -NoProfile -File scripts/check-changed.ps1
pwsh -NoProfile -File scripts/check-changed.ps1 -Base <已核实的提交>
```

从子目录调用时，将脚本路径换成能定位它的相对路径或绝对路径。默认基点 HEAD 只检查暂存、工作区和未跟踪文件；指定基点额外包含其与 HEAD 的 merge-base 差异。`-ListOnly` 显示范围及计划命令，不运行检查器。

脚本验证基点，保留包含中文/空格的完整路径，过滤删除项与目录后才将文件传给检查器。没有适用文件时直接结束；任一原生命令失败立即返回失败，不能用后续成功命令覆盖退出状态。

前端调用已有 ESLint/Prettier，并通过 build 执行两份 TypeScript 检查；后端调用已有 Ruff/格式和 Pyright。Prettier 使用 `--end-of-line auto` 兼容本地 CRLF 与 CI LF，其他格式检查保留。相关配置或依赖变化会明确切换到对应域全量检查，删除 TS/Python 文件仍进行类型检查。Rust、业务回归和真实桌面验收不在该脚本范围，按触及模块已有入口执行。脚本自身改动运行 `scripts/test-check-changed.ps1`。

## CI 与失败处理

### 本地与 CI 共用的测试入口

依赖安装沿用 frozen lockfile；最终验收和基点比较使用同一个入口：

```powershell
uv run --frozen --directory backend python -m scripts.run_tests all
uv run --frozen --directory backend python -m scripts.run_tests frontend src/pages/chat.test.tsx
uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_context_retrieval.py
```

`all` 顺序执行两套测试，前端固定单 worker；测试失败后仍执行另一套，超时或中断则停止后续执行。单套支持文件或 pytest node ID 筛选，不能传额外运行器参数改变验收条件。全量、基点安装和基点复测等耗资源任务顺序执行；轻量只读检查可并行。筛选运行只证明该范围，不替代全量。具体参数以 `backend/scripts/run_tests.py` 为唯一来源，CI 直接调用它。

每次执行输出 `.pytest-tmp-runs/<时间-随机标识>/<suite>/`，包含：

- `tests.log`：运行器详细进度及结束时的慢用例耗时。运行期间可用 `Get-Content <日志绝对路径> -Tail 30 -Wait` 观察；后端输出不缓冲，长用例由 pytest 的 faulthandler 打印线程栈。
- `result.json`：源码提交、脏工作区标记、完整命令、工作目录、开始/结束时间、PID、耗时、时限、原生退出码和状态。

默认每套上限一小时，`--timeout <秒>` 可缩短诊断运行；这不是单个业务测试的等待时间。超时终止本次子进程树并返回 124，中断返回 130；原生测试失败码继续传播。`FAILED`、`TIMED_OUT`、`INTERRUPTED`、`START_FAILED` 分别记录，不能统称为测试失败或通过。外部强制终止来不及完成记录时，`RUNNING` 仅表示缺少结束证据。记录中的脏工作区标记不是源码快照，需要连同本次 diff 固定证据。

基点使用其自身的同一入口及独立依赖，保存当前和基点两个结果目录；最终记录引用原命令、状态及失败形态。临时数据库单独放在 backend 专用 basetemp，不混入日志目录，不自动删除用户资源。已有历史失败仍按原规则复核，不增加豁免。

手动全量测试的 `tests` job 在结束时保存上述日志目录，测试失败也执行，保留七天；没有启动测试时不伪造报告。上传范围只包含运行记录与测试日志，不包含 basetemp 数据库、依赖或用户数据。

[Checks 工作流](../../.github/workflows/check.yml) 在 push、PR 和手动触发时使用 Windows runner、只读仓库权限、锁文件安装依赖。自动运行的 `checks` job 只执行改动范围检查、API 契约和双语一致性；`tests` job 仅在 Actions 页面手动 Run workflow（`workflow_dispatch`）时执行，复用已有 FFmpeg 准备脚本及前后端全量测试入口，保留全部用例。脚本自身改动仍在本地运行自检；Agent 相关改动按下文运行已有针对性回归。轻量检查通过只证明上述范围，不代表全量测试通过；已执行的检查失败仍保持红灯。

新增工作流并不等于远端已经执行或已经设置分支保护。首次 push 后核对 Actions 的安装、用例、跳过项和结果；若需要合并强制门禁，再在仓库设置中指定所需检查。

干净依赖安装曾复现聊天 Markdown 插件的 `unified` 11.0.0/11.0.5 类型冲突；现在由 `pnpm-workspace.yaml` 的精确覆盖统一为已使用的 11.0.5，并同步锁文件。验证依赖调整时采用独立安装和现有 Markdown 消费回归，不能仅以旧 node_modules 构建通过作证。覆盖语法依据 [pnpm 官方文档](https://pnpm.io/settings/dependency-resolution#overrides)。

全量失败先固定当前提交及命令，再在基点复现同一失败用例。记录错误形态、环境、耗时及是否重现，区分本次回归、稳定历史失败和并发/资源超时。历史失败保留在其实施或验收记录中，不能靠扩大超时、忽略整个文件或过滤全套测试获得绿灯。

目前已有失败的复现记录见 [上下文管理 01](../../.scratch/agent-context/implementation.md#验证结果)：后端 document_import 日志断言、quiz_last_count 响应断言、second_sidecar 超时，以及前端设置超时和部分旧界面断言。该记录是固定基点证据，不是永远有效的豁免名单；CI 不过滤它们。

2026-10-12 复盘接线时，全量前端 lint 另发现 `PlanDraftEditor.tsx:55` 和 `LearningPlanTab.tsx:760` 的 Fast Refresh 导出警告；两文件与本次基点 HEAD 字节一致，未修改它们或放宽 `--max-warnings 0`。记录见 [本次实施](../../.scratch/agent-context/retro-implementation.md)。

## 隔离基点

1. 固定当前 HEAD、比较基点、工作区改动与工具版本。检查运行所需源码是否已跟踪：干净检出缺文件时先定位 ignore/生成链，不把复制本机源码当作可复现通过。
2. 在当前仓库外的同级目录建立专用 detached worktree，明确绝对路径和用途。例如仓库根执行：

   ```powershell
   $baselinePath = Join-Path (Split-Path -Parent (Get-Location).Path) 'KnowRealm-AI-baseline-<任务名>'
   git worktree add --detach $baselinePath <基点提交>
   ```

3. 在基点安装独立依赖：`pnpm install --frozen-lockfile`、`uv sync --frozen --directory backend`。可共用包缓存；node_modules 和 .venv 属于各自 worktree，不建立指向当前工作区的 junction，也不借用当前源码或依赖环境冒充干净检出。
4. pytest 使用该 worktree 内独立 `.pytest-tmp-<任务名>`；长命令保留退出码和日志路径，先读失败摘要，必要时再读取对应堆栈。不同测试进程使用不同 basetemp。
5. 创建时记录要清理的 worktree、测试目录与自启进程。清理前退出自建进程，核对解析后的绝对路径确实是本次专用目录；核对链接类型与目标，先移除链接本身，避免递归遍历其他工作区。仅清理自己创建的资源，保留用户已有 worktree 和脏改动。
6. 清理被权限或策略拒绝时，报告原动作、拒绝原因和残留路径，不换删除方式绕过拒绝。证据记录清理状态，不能宣称工作区干净。

## Agent 装配变更

改动模型 Middleware 的顺序、默认摘要、文件卸载或上下文组装时，先从真实 `build_agent` 装配路径验证模型最后收到什么，再检查配置名称或局部函数。复用 [test_context_budget.py](../../backend/tests/test_context_budget.py)、[恢复回归](../../backend/tests/test_chat_turns_recovery.py) 和 [工具预算回归](../../backend/tests/test_tool_budget.py)。其中 90k JSON 用例覆盖完整结果进入下一次请求或被预算拦截，不能只用小结果证明框架默认行为。

供应商、密钥、外发同意变化的恢复行为仍按既有入口验收；模型替身验证确定性边界，真实供应商验证实际用量与语义效果，两者分别记录。

预算测试在执行轮次前先验证夹具的场景前提：使用生产完整输入计量，确认实际工具定义参与计量、输入是否触发压缩、原输入应能容纳还是应超限。前提变化应明确报告实际输入、预算和工具成本，先校准场景，保留独立的预算边界、重试次数和持久消费断言；不扩大等待超时来掩盖场景变化。现有例子为 `test_conversation_compaction.py` 的 `assert_compaction_fixture`。

## 验收证据

开工时在当前工单中明确至少一条完整验证路径：真实生产入口 → 处理/裁剪 → 持久化 → Tool/API 消费 → 模型输入或页面。列出测试数据、替身边界、通过条件和证据位置。优先复用已有夹具及测试；模型/网络替身只替换外部边界，不绕过本票要验证的生产处理。

桌面票同时给出可重复的人工步骤和固定测试数据；每项记录 `PASS / FAIL / NOT_TRIGGERED / NOT_RUN`。大输出、自动压缩等未触发时记 `NOT_TRIGGERED`，模型未实际调用 Tool 时不能证明取回或权限拦截。03 的示例见 [桌面验收步骤](../../.scratch/agent-context/03-desktop-acceptance.md)。

工单清单旁注明证据层级；勾选表示该条声明的范围通过。把尚需真实验证的要求拆成独立未勾选条目，避免统一勾选后仅在末尾补免责声明。示例：

```markdown
- [x] 公开 API、迁移 SQLite 与 Worker 的超限拦截通过（模型替身，记录见 implementation.md）。
- [x] 四主题与窄窗布局通过（浏览器模拟）。
- [ ] 真实 Tauri/WebView2 往返及 Windows 125%/150%/200% 系统缩放，待真实验收。
```

记录实现状态、自动化、模型/网络替身、真实 API/SQLite/Worker、真实模型、真实 Tauri/WebView2 和 Windows 系统缩放，按实际取得的证据填写。浏览器 viewport/DPR/字号不能代替 Windows 缩放；供应商缺 usage 填未知；未实施的后续票不随当前票关闭。
