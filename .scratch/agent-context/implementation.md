# 上下文管理工单 01 实施与验收

2026-10-12；范围仅为 `issues/01-model-budget-and-context-view.md`。原基点 `e2dcc3a093b9b26cf6bf9364f7728b7394b1c1bc`，当前分支 `feat/extend-dev-09`。第一份实现提交 `a5f84b5`，后续提交收口审查修正、关联夹具及交接记录。

## 已实现

- AI 服务设置保存端点/模型绑定的输入上限、总窗口、输出上限以及回答/摘要输出额度；默认 4096/1024。仅对已核实的官方端点 `qwen-plus`、`gpt-4.1` 提供可信能力及来源，覆盖优先；兼容/未知部署必须显式配置，不按同名模型推断。端点/模型变更清除旧覆盖；同身份且未提交预算字段时保留已有配置。
- 0046 为纯 DDL：会话上下文状态、轮次策略及初始输入快照、逐次模型请求计量三表。按需初始化，不批量调用模型或重写历史。缺少新兼容标记的旧活跃轮次进入既有兼容等待，保留原消息及消费事实。
- 主 Agent 的最内层 `InputBudgetMiddleware` 在每次完整模型请求前计量最终系统提示、材料/记忆、全部消息、工具定义及协议开销；输出额度通过框架 `ModelRequest.override` 下传。超限持久记为 BLOCKED 并拒绝模型调用，已受理 USER 消息保留。原六次工具/字符/独立提交预算保持有效。
- 使用官方 `FilesystemMiddleware` 关闭大消息和工具结果卸载；完整业务 JSON 进入下一次检查，不替换为当前不可读取的文件指针。原默认摘要禁用保持；自动摘要、历史取回、固定、排除及重置由 02～05 实施。
- 新轮次同事务绑定策略和输入版本，首次执行固化初始消息；恢复沿用原输入和策略。当前供应商身份、外发同意、记忆开关及持久取消/执行身份继续校验。同端点同模型换密钥并重新同意后可恢复；每次调用核对本次模型实例的凭据指纹，执行中再次改变配置仍拒绝外发。
- 公开 GET `/api/chat-sessions/{sessionId}/context` 及 POST `/context/estimates` 复用现有上下文 Service/AgentConfig，后者接收草稿、联网开关和页面提示。查询区分逐次实际请求与下一轮预估，展示轮次 ID、绑定上下文版本、策略版本、预算来源与组成；无 usage 显示未知。模型调用本身自动经过 Middleware；后续管理/取回 Agent Tool 由对应票接入，普通查看不消耗工具次数。
- 聊天标题进入独立 `/chat-context/$sessionId` 页面，可切换会话和返回。头部/选择器固定，实际/预估 Tabs 各自滚动，视图放 URL；按会话保存内存草稿，正文不放 URL、不写浏览器持久存储。导航复用原订阅生命周期，关闭观察不取消后台轮次。
- 复用现有 shadcn/Base UI、主题语义变量、错误恢复入口及减少动效规则；双语、错误登记及 OpenAPI 生成物同步。未新增依赖，未修改 rules、DESIGN、ADR 或术语表。

## 计量与能力边界

当前仅实现明确标注为 APPROXIMATE 的 UTF-8 字节近似计量：`ceil(bytes / 2)`，工具 schema 和协议另计；可用输入为 `min(I, C - O) - ceil(20% * min(I, C - O))`，忽略未知的 I/C 项。输出按已知 M/C 收紧。尚无可靠 tokenizer 适配，因此没有以 10% 余量声称精确计量，也没有静默下载模型资源。20% 余量不能保证覆盖所有供应商/特殊文本的估算偏差；供应商计费以实际 usage 为准。

可信能力依据：[阿里云 qwen-plus](https://help.aliyun.com/zh/model-studio/qwen-plus)、[OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)，本次查阅官方来源后绑定精确端点/模型。名单需要随供应商更新维护。

## 验证结果

### 真实 API / SQLite / Worker + 模型替身

- 最终 `test_context_budget.py`、`test_chat_turns_recovery.py`、`test_tool_budget.py`、`test_error_code_guard.py`：**51 通过**。走公开提交/查询/取消/恢复、真实迁移 SQLite 和 Worker；模型为 Stub，不是真实供应商。
- 覆盖策略绑定、实际与下一轮配置分离、未知能力拒绝、完整工具循环计量、超限零调用及 USER 保留、原快照恢复、取消及身份保护、原预算跨恢复、旧迁移兼容。新增 90k 合法 JSON 两种场景：完整进入第二次模型请求，或第二次被阻止且无部分裁剪。
- 全量一次：**1191 通过、10 失败**；随后 7 项相关失败逐项复验通过，其中适配了新能力配置/响应字段和回拨迁移夹具，修复了密钥重新同意后的恢复回归；长材料用例单跑通过。
- 剩余 3 项在原基点复现：document_import 日志隐私断言、quiz_last_count 偏好完整响应断言、second_sidecar 10 秒进程等待超时。未借本票修改这些领域。基点使用原安装依赖与独立 basetemp。

### 前端自动化与静态门禁

- 最后相关批次：**90 通过、1 失败**（4 文件）；唯一失败为设置页既有“控件即改即存”15 秒超时，原基点同用例单跑也重现。
- 最终新增页面导航用例单跑通过：A 草稿→独立页→下一轮 Tab（URL）→切换 B 保留视图→返回 B→写 B 草稿→返回 A 保留原草稿，正文未进 URL。
- 前端全量一次：**718 通过、10 失败**（79 文件）。供应商保存请求断言已随新预算字段适配并复验；7 项原有失败在基点重现（设置超时、CourseBrainReview、LearningPlanTab 三项、RecordDetail、CommandPalette）。另外 CourseBrainMastery 与 SharedRefsTab 在基点批次通过，最终两文件重跑 **12 项通过**。
- 触及文件 Ruff/格式、生产文件及新增上下文测试 Pyright、触及前端 ESLint/Prettier、OpenAPI 导出一致性、双语及错误登记门禁通过；最终 `pnpm build`（含两份 tsc）通过。构建仍有既有路由测试文件提示与大 chunk 提示。
- `test_chat_turns.py` 的 5 项 unused-variable Pyright 错误在基点同文件复现；未为本票清理既有测试变量。范围 Pyright 不宣称全仓类型检查通过。

### 浏览器视觉与交互模拟

使用真实前端组件、浏览器 HTTP/Tauri 桥替身和合成预算展示数据；不是真实桌面或供应商。目检截图仅工具内展示，不宣称已经保存可交付的截图文件。

- 四主题 LIGHT_DEFAULT / DARK_DEFAULT / LIGHT_SAGE / DARK_INK；zh/en；1440×900、1099×720，18px 字号，页面无横向溢出。最终固定头部/选择器不随详情滚动。
- 549×360、18px 英文 DARK_INK 模拟：窄窗紧凑头部，详情区有 102px 可滚动高度，返回/配置动作可达。
- 原生浏览器键盘选择器 Enter/Escape；最终 Tabs ArrowRight/Enter 切换后 URL 为 `?view=next` 且焦点保留。`prefers-reduced-motion` 为 true；沿用无空间过渡和既有全局减少动效样式。
- 展示 fixture 的下一轮数据用于布局，不作为真实预估正确性的证据；预估正确性由前述 API/SQLite/Worker 用例单独验证。

## 两轴审查

### Standards

3 项已修复并经只读复核闭合：预估 query key 补齐草稿/联网/页面参数；固定导航/会话选择并改为局部滚动；请求状态统一 StrEnum、ORM 和公开 Schema，删除状态 Any 转换。未发现新增实质规范问题。

### Spec

2 项已修复并经只读复核闭合：框架大结果卸载导致完整 JSON 未计量，改为官方配置禁用卸载并增加 90k 回归；页面补齐实际轮次和绑定输入版本。后续密钥恢复修正另经规格代理复核，当前实例指纹及原同意边界保持。审查代理没有代替主任务运行测试或验收真机。

## 仍待 06 验收

真实模型/外网调用与供应商 usage 校准、真实 Tauri/WebView2 持续生成时独立页往返/取消/等待恢复、四主题及 Windows 125%/150%/200% 系统缩放。浏览器视口和字号模拟不能代替这些验收。工单 01 的实现收口不代表整条上下文管理或工单 06 已完成。

临时文件清理被自动审批策略拒绝（返回 `blocked by policy`，无细分原因），缩小为单独移除已核验 junction 后仍被拒绝；未继续尝试其他删除途径。`.scratch/agent-context/baseline/` 隔离基点 worktree 及 `evidence/ui-fixture.json` 保留且不纳入提交；该 fixture 为旧版布局数据，不是最终 API 契约证据。两个依赖 junction 仅指向原工作区依赖，原依赖目录保持可用。临时 Vite 进程已停止。
