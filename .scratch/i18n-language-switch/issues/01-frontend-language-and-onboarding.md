# 01 — 前端语言链路与向导语言步骤

**What to build:** 学习者在设置页外观分组把界面语言在「中文 / English」间切换，全应用文案（侧栏、命令面板、资产库、捕获流程、确认对话框……）即时跟随、无需重启，重启后仍记住选择。首次启动向导变为四步——第一步选界面语言（预选系统语言，跳过=接受预选），存量用户升级后界面保持中文且无闪变。切换语言时系统托盘菜单同步重建（显示/退出 ↔ Show/Exit），`<html lang>` 跟随。同时把「内容语言跟随输入」固化为显式 prompt 指令：中文材料的总结 / 知识点 / 习题仍是中文，英文材料出英文，对话回答逐条跟随用户消息语言——与界面语言正交，不做内容翻译。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 后端偏好读 / 写模型新增 `language`（枚举 zh | en，缺省 zh），openapi 导出后 api-types 重新生成
- [x] 设置页外观分组两选 RadioGroup，复用「改动即 PUT、成功回写缓存、失败回显服务端事实」的既有偏好控件模式；切换即时生效
- [x] 首帧语言 = localStorage 缓存 ?? 系统语言（navigator.language 以 zh 开头 → zh，否则 en），偏好 GET 成功后校正并写缓存
- [x] 存量升级（无 language 值）读取即 zh，界面无闪变
- [x] 向导四步：语言步预选系统语言，完成 / 全部跳过时 PUT 当前选中项
- [x] 切换语言时经 command 通知壳层重建托盘菜单（显示 / 退出 ↔ Show / Exit）
- [x] `<html lang>` 随界面语言切换
- [x] 全部 LLM prompt 模板（总结 / 知识点 / 习题 / 评分 / Todo / 复习资料 / 对话）统一追加「用与输入内容相同的语言输出」显式指令；Fake 模型 prompt 断言覆盖
- [x] vitest setup 固定界面语言 zh（CI 的 en-US 系统语言不炸现有中文断言）
- [x] en.json 以 zh 结构副本落位（key 对齐占位，真实翻译归 02）
- [x] 测试过 spec 缝隙 1 / 2：语言控件 PUT 请求体与文案切换、向导步骤流、首帧 hook 迁移路径（缓存命中 / 未命中 / 校正）
- [x] 门禁全绿（tsc / lint / prettier / vitest / pytest / ruff / pyright）
- [x] PRD 决策表新增「界面语言与内容语言」条目并升版，同步全部交叉引用

> 并行备注：本票可与 03 并行（不同层零逻辑耦合）；prompt 模板文件与 03 的 raise 替换同文件不同区域，git 可自动合并；api-types 生成物若撞，后合并者重新生成即可。

## 实现备注（2026-09-08）

- 落点：偏好字段 `backend/app/modules/settings/{schemas,config}.py`；首帧与校正 `src/i18n/language.ts` + `src/i18n/index.ts`（`applyLanguage` / `syncLanguageWithPreference`）；托盘 `rebuild_tray_menu` 命令（lifecycle.rs，按 `tray_by_id` 原地换菜单，事件协议不动）。
- 「文案随之变化」断言受 en.json 占位（值=zh）所限，测试断言到机制层（PUT body + i18n 实例 + `<html lang>` + 缓存）；真实英文文案断言随 02 翻译落位后补。
- prompt 指令共享常量在 `backend/app/shared/prompts.py`；对话域独立措辞 `CHAT_LANGUAGE_INSTRUCTION`（跟随最新提问），在 build_context_messages 预算计量前统一附加到有效 SYSTEM，挂载与自由聊天一处覆盖。
- 判断题选项 `["对","错"]` 是 schema 数据契约（quiz/schemas.py 校验恒为对/错），prompt 中显式标注为唯一不随语言变化的例外；英文试卷的判断题选项仍为对/错，如需英文化须改契约（本票未做）。
- prompt_version（summary-v1 等）未随本次 prompt 修订递增：版本串用于 llm_call_logs 溯源，递增会波及多处结果断言；如需按版本区分本次语言指令修订，后续统一 bump。
- 完成向导时语言 PUT 失败与 completeOnboarding 同样阻断并提示（重试语义一致）；否则下次启动会被偏好校正回旧值。
- 托盘 rebuild 失败仅 console.warn 降级（文案已生效，托盘旧标签等下次切换或重启自愈），不阻断语言切换。
- vitest setup 的语言复位对 node 环境测试做了守卫（`typeof window`），否则纯逻辑测试在 setup 顶层导入 i18n 即崩。
- 遗留：`docs/rules/desktop-react.md` §5 仍写「语言（V1 仅中文，设置页隐藏）」，与 #59 矛盾；rules 按惯例随下次发布镜像流程同步（本票按 AGENTS.md 约定不改 rules 文件）。
- 全量 vitest 中 `SidebarUserArea.test.tsx` 一个用例失败为工单 03 并行改动区既有问题（干净树复现），非本票引入。

## 用户真机验收（agent 不代勾）

- [ ] 切换即时生效、无需重启，托盘菜单跟随
- [ ] 首启向导四步流（英文系统预选英文）
- [ ] 存量升级无闪变
- [ ] 中文材料 + 英文界面 → 生成内容仍为中文
