# 工单 01：Agent 时间能力 v1（时间提示行 + 时间工具族 + 计划锚点本地化）

状态：done（自动化门禁全绿；真机验收单列下方，不由 agent 代勾）
标签：ready-for-agent → done
日期：2026-09-30

## 背景与决策（grill 定案）

核验事实：agent 此前无任何时间能力——29 个工具无时间工具、prompt 无时间注入、
deepagents 内置工具全屏蔽，模型不知道"今天几号"；学习计划铺排锚点用
UTC 日期（3 处 `datetime.now(UTC).date()`），本地 UTC+8 每天 0:00~8:00
提交会整体偏一天。

GPT 方案评分 7/10：方向正确（时间属上下文、IANA、tzdata、aware、clock 注入
测试），但三盲区——不知 SYSTEM 行落库跨轮重建（时间写进落库正文隔天陈旧）、
不知 AgentRuntimeContext 已存在（平行体系多余）、DateTimeService 七方法
无消费者（YAGNI）。用户定案：轻量版 + 多工具（不建 Service 类，共享纯函数
helper，listing.py 先例）；时间行到秒（HH:mm:ss）；锚点连带修；直连 implement。

关键实现定案：

- **时间提示行**：`build_context_messages` 新增 `time_hint` 动态段（页面提示
  同款每轮重建、不落库），位置在动态段最前（learner/page_hint 之前）；
  内容=用户时区当前时间到秒+星期+指引（陈旧时调工具）。prompt_version 双
  bump：chat v21→v22、research v22→v23。
- **用户时区**：`settings.config.resolve_user_timezone(data_dir)`——偏好
  timezone（IANA，已有字段零消费）优先，未设置/坏值回退系统本地（Windows
  固定偏移 timezone 对象，展示名走 `timezone_label`）。链路：accept 读一次
  → AcceptedMessage.user_timezone → _session_context（生成 time_hint）+
  AgentRuntimeContext.user_timezone（工具默认时区）。
- **四个只读工具**（tools/ 平铺一文件一工具，共享 time_utils.py）：get_current_time
  （可选 IANA 参数）/ convert_time（时区换算，naive 按 from 或用户时区解释）/
  shift_datetime（墙上钟点平移，DST gap 按 PEP 495 fold=0）/ diff_datetime
  （正负差+总量）。全部计入 calls_used 预算（超限软引导 ok=True，检索先例）、
  返回 {ok, ...} 结构化 JSON；无效时区名 ok=false 中文错误。
- **锚点本地化**：三处（generate_learning_plan / regenerate_plan /
  plan_confirm×2）统一 `local_today()`（系统本地日期）。**两口径**：偏好时区
  只用于提示行/工具；锚点不读偏好——流外确认链（端点→ProposalService.confirm
  →registry→submission_validator）不可达 data_dir，动 5 层框架签名违背精准
  修改；默认用户（timezone=null）两口径天然一致，显式跨时区设置差异为已知
  边界（凌晨窗口提示行与锚点可能差一天，generate 与 confirm 互相校验仍同源
  自洽）。

## Checklist

- [x] settings/config.py：resolve_user_timezone（偏好优先/系统回退）
- [x] tools/time_utils.py：timezone_label / local_today / parse_datetime_arg /
      resolve_timezone_arg / weekday_label / format_time_hint / time_payload
- [x] 四工具：get_current_time / convert_time / shift_datetime / diff_datetime
- [x] AgentRuntimeContext.user_timezone + AcceptedMessage.user_timezone +
      accept 读取 + stream_events 绑定
- [x] context.py time_hint 动态段（到秒）
- [x] graph.py 恒挂载段挂四工具；prompt_version v22/v23
- [x] 三处计划锚点改 local_today()
- [x] 测试：tests/test_agent_time.py 28 用例（helper/工具/预算/提示行注入/
      偏好时区解析；DST 固定样例=美东 2026-03-08 gap 与 2026-11-01 切换边界）
- [x] 既有测试同步：test_chat_streaming 版本断言+字节一致测试剥离时间行+
      7 处工具可见性矩阵；test_research_session 版本断言
- [x] CONTEXT.md 词条「时间提示（Time Hint）」；PROJECT_PROGRESS 更新
- [x] 门禁：pytest 全量 / ruff / pyright / openapi --check

## 用户真机验收（单列，不代勾）

- [ ] 对话问「今天几号 / 现在几点」：不调工具直接答对（时间提示行生效）
- [ ] 问「东京现在几点」「3 天后是几号」：调对应工具、答对
- [ ] 设置页改时区后下一轮对话生效（每轮重读）
- [ ] 本地凌晨 0~8 点生成学习计划：铺排从当天起（不再偏一天）
