# 02 — 调整、确认与跨重启 HITL

**What to build:** 用户可以针对待确认总结输入反馈生成新版，在应用重启或隔天后继续 review，并以幂等事务确认当前版本；确认后 Record 完成、学习事件落表、今日待办移除，而未实现的后续能力继续诚实禁用。

**Blocked by:** 01 — Provider 配置与首次总结待确认

**Status:** done

- [x] 调整请求携带当前 summary_id 与 1～1000 字反馈；旧版本或空白/超长反馈被拒绝。
- [x] 每次调整创建独立 Summary Job，以同一 Transcript、上一版和反馈生成新版；成功后才将上一 GENERATED 标记 SUPERSEDED，失败保留旧版 SUMMARY_READY。
- [x] Graph thread 按 record_id + source_version 隔离，interrupt/resume 使用同一 thread；应用完整重启后仍可继续调整或确认。
- [x] 确认携带当前 summary_id，并在一个事务中落 Summary=CONFIRMED、Record=COMPLETED/confirmed_at 与 SUMMARY_CONFIRMED Learning Event。
- [x] 重复确认返回同一结果且不重复事件；旧版本确认/调整返回 409，事件幂等键全表唯一。
- [x] API 提供当前 Summary 与历史版本列表/详情；桌面端当前只渲染可操作版本。
- [x] 今日页真实列出 SUMMARY_READY 待办并直达 Record Summary；确认后通过查询失效立即移除。
- [x] COMPLETED 只解锁后续能力的状态门禁，未实现入口保持明确禁用，不增加死按钮或假成功。
- [x] ASGI、SQLite、AsyncSqliteSaver 重启恢复、MSW 用户行为及无障碍交互测试通过。

## Verification

- 后端：`111 passed`（新增调整版本链/失败保留旧版+复用失败 Job/幂等确认+事件/三次完整重启 resume/中断恢复/今日待办）；Ruff 与 Pyright 通过，OpenAPI 契约检查同步。
- 桌面端：`51 passed`（新增调整→新版本→确认全流程、409 旧版本提示并刷新、今日页待办直达与确认后失效移除）；TypeScript build 与 ESLint 通过。
- 调整 resume 由 AsyncSqliteSaver 持久 thread 上的 `Command(resume)` 验证（三次应用重启）；未调用真实 Provider，全部由可注入假模型证明。
