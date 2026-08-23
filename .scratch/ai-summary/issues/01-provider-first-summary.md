# 01 — Provider 配置与首次总结待确认

**What to build:** 用户可以在 Record Summary 中配置并测试一个 LLM Provider、明确同意 Transcript 外发，然后让一条真实 SUMMARY_PENDING Record 在 2 秒内取得 Summary Job，经固定结构化 Graph 生成首版总结并进入 SUMMARY_READY；缺配置、缺同意、归档课程和无效端点都有诚实可恢复的界面。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 数据库迁移提供 llm_call_logs、learning_events 与 Summary 所需约束；fresh/upgrade user_version 一致，ai_summaries 继续作为版本事实表。
- [x] 最小 Provider API 原子保存地址、密钥和模型，读取时屏蔽密钥，空密钥保留、显式清除，连接测试使用合成文本与正式 Summary Schema。
- [x] LLM 外发同意绑定 Provider 指纹；缺 Provider/同意时不创建 Job，Summary API 返回明确 action_required。
- [x] SUMMARY_PENDING + Transcript + ACTIVE 课程在正常首次来源完成后自动创建一个 Summary Job；显式提交 2 秒内返回 202 与 job_id，重复提交不产生并行 active Job。
- [x] SummaryWorker 使用固定 StateGraph、AsyncSqliteSaver、版本化 Prompt 和统一 LLM 埋点生成首版不可变 Summary；Record 进入 SUMMARY_PROCESSING 后最终到 SUMMARY_READY。
- [x] Summary Pydantic Schema 严格校验 topic、abstract、sections/headings/points；无效输出不入库、不自动追加调用。
- [x] 写回前再次校验 Record、ACTIVE 课程和 Transcript source_version；迟到结果 CANCELLED 且不保存正文。
- [x] Record Summary 页签覆盖配置、同意、生成、处理中、失败与待确认状态，复用现有 SSE/REST 失效链，不创建第二条流协议。
- [x] 后端 ASGI/SQLite、Graph 假模型和桌面 MSW 行为测试通过；报告不会把假模型证明成真实 Provider 成功。

## Verification

- 后端：`105 passed`；Ruff lint/format 与 Pyright 通过。
- 桌面端：`46 passed`；TypeScript build 与 ESLint 通过。
- 真实本地链：Vite + sidecar + SQLite 验证 Provider 保存、密钥遮蔽、授权披露；1440/820/640 与系统深浅色渲染无横向溢出。
- 未调用真实 Provider；结构化生成成功由 Graph 假模型证明，不作为真实第三方成功证据。
