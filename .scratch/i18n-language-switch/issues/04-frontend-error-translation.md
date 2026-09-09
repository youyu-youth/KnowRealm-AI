# 04 — 前端错误翻译消费与壳层错误码

**What to build:** 全覆盖闭环：英文界面用户的所有错误提示都是英文——API 错误（如「请先配置 LLM Provider」→ 英文）、对话流式错误、Rust 命令错误（录音电源管理等），按 03 落定的错误码在前端统一翻译；中文 detail 降级为码表未命中时的兜底原文。所有现有错误展示点零改动自动受益（翻译收敛在错误构造层单一入口）。

**Blocked by:** 02（en 文案资源）, 03（错误码值集与契约）

**Status:** done

- [x] ApiError 构造层统一翻译：命中码表 → 按码 + params 插值取译文；未命中 → 回显 detail 原文；i18next 实例在 React 外可用
- [x] errors 命名空间 zh / en 文案对齐 03 的全量错误码清单（前端单一文案来源）
- [x] 对话 SSE 错误载荷经同一入口翻译（onError 展示翻译文案）
- [x] Rust 命令用户可见错误（录音电源管理、sidecar 透传等约 5 条）改为 `CODE: 明细` Display 协议，前端码表翻译（仿数据目录迁移错误码表的既有模式）
- [x] 单元测试过 spec 缝隙 3 / 4：构造层翻译与回显、SSE 载荷翻译；组件端到端用例（mock 响应带 code → 界面显示翻译文案）
- [x] 门禁全绿（tsc / lint / prettier / vitest）

## 实现备注（2026-09-09）

- **落点**：`services/http/apiErrorMessage.ts`（翻译入口单一出口：i18next 默认单例 + `isInitialized` 守卫——不顶层导入 `@/i18n`（其 init 读 window），node 环境纯逻辑测试导入本链路不炸，未初始化一律回显原文）；`client.ts` ApiError 增 `code` / `params` 字段、message 构造期翻译；`chatSessions.ts` SSE error 事件走同一入口并按 ADR-0017 透传可选 params；展示点零改动（消费 `error.message`）。
- **errors 命名空间 110 键**（104 业务码 + 4 通用 + 3 SSE），zh 对齐清单文案；码值经 AST 一次性脚本从后端源码核对（同一码后端多措辞，如 `COURSE_ARCHIVED` x9 → 前端取清单单一文案），脚本用后已删。
- **Rust 壳层 4 码**：power.rs 三码（`RECORDING_POWER_THREAD_UNAVAILABLE` / `RECORDING_POWER_RESULT_MISSING` / `RECORDING_POWER_SYSTEM_CALL_FAILED: OS明细`）+ sidecar.rs `EXPORT_ARCHIVE_MISSING: 路径`；清单文档补「壳层命令码」节。前端码表 `services/tauri/commandErrorCopy.ts`（仿 migrationErrorCopy 模式），消费点：RecordingExperience 释放路径全量 + 启动路径字符串 reject 分支、useDataDirectoryFlows 导入归档（未命中保持原文回显）。
- **有意的不对称**：录音启动路径 Error 实例（构造层已翻译的 ApiError、本地化的麦克风错误）不走码表——解析会把具体译文吞成通用兜底文案；invoke 字符串 reject 才需码表。code-review 两轴标注的同点已按此裁定。
- 「对话事件流没有响应正文」硬编码中文改英文技术串（传输层防御分支，与 abortError "Aborted" 同类），code-review 标注为计划外行为变更、已接受。
- code-review（两轴）：无 hard violation；采纳修复 SSE params 透传；commandErrorCopy 与 migrationErrorCopy 三行解析同形判定为「仿既有模式」预期内不抽共享。
- 门禁：tsc 双 tsconfig / eslint --max-warnings 0 / prettier（改动文件）/ vitest 41 文件 379 用例全绿 / cargo check + cargo test 21 全绿。

## 用户真机验收（agent 不代勾）

- [ ] 英文界面下触发各类错误（未配置供应商、归档课程操作、参数校验失败、对话发送失败）抽查全英文
