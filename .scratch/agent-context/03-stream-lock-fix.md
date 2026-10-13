# 03 真机反馈：回答末尾卡住并失败

基点 `7aac182`。修复范围仅 ChatTurn 事件刷新任务的停止收口及对应回归，不改检索、工具预算、模型/数据库超时、页面展示或用户数据。

## 真实现场

数据目录 `E:/knowrealm-export-acceptance/测试`，会话 `3a483180-ff25-4c0e-8dba-cdae1f59acf0`，失败轮次 `30b2cc75-fc70-4b32-a317-ec6310bc95fe`。截图中模型转述的 `5ef29df8-519e-46fc-803e-c9cc1d7637d6` 实际是上一轮 turn 身份，不是会话身份；诊断以数据库所属关系为准。

- 16:32:40 开始，search_context/read_context 两工具已返回；三次 ANSWER 请求均为 COMPLETED。
- 最后一条持久 token 为 16:32:54；16:33:00 首次执行失败。日志栈明确停在 `ChatTurnService.finalize_completed` 的条件 UPDATE，底层报 `sqlite3.OperationalError: database is locked`。
- 上下文页查询的初始化 INSERT 随后也受锁阻塞，Worker 失败收口重试；到 16:36:29 才落 FAILED / CHAT_STREAM_FAILED。没有将其归因为网络/模型超时。
- 原会话、历史消息和失败事实只读核对，未修写原轮次或删除部分回答。

## 原因与修复

`_drive` 结束观察时直接 cancel 定时 token flusher，且未等待其结束。flusher 当时可能已在 `append_events` 的提交阶段；取消数据库提交后，完成写入先开始，SQLite 锁与事务清理仍未收口。后台线程执行的 aiosqlite 提交和上层 asyncio 取消并不等价于事务已经释放。

定时刷新改为 Event 通知停止；正在进行的事件提交正常完成，执行侧 await flusher 后才保存最终回答或进行停止/等待收口。重试进入同一 executor 的 `_drive` 时清除停止通知；取消观察器也 await 清理，不遗留未收口任务。原完成处的取消/claim 原子校验、事件提交后通知及停止恢复语义保持。

## 验证

- 新增 `test_answer_completion_waits_for_inflight_token_commit`：真实 API、迁移 SQLite 和 Worker；模型事件为最小流替身，驱动提交边界延迟以固定交叠时序，事务/seq/最终回答写入仍为生产路径。旧代码明确触发“回答完成取消了仍在持有 SQLite 写锁的 token 提交”（`03-stream-lock-red4.log`），修复后通过（`03-stream-lock-green2.log`）。这个确定性回归证明事务停止顺序，不能单独等同于真机复现全部 3 分 48 秒耗时。
- 原事件写入、03 取回、ChatTurn 控制与恢复：48 项通过，177.67 秒。命令：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_chat_turn_event_writes.py tests/test_context_retrieval.py tests/test_chat_turns.py tests/test_chat_turns_recovery.py --timeout 600`。结果目录 `.pytest-tmp-runs/20261013T085504Z-60d7d6ab/backend/`。
- 触及 Ruff/格式/Pyright 0 错误通过（`03-stream-lock-gates.log`）。未改 API 契约、前端或业务迁移。
- 真实模型回放：复用已授权供应商配置，在隔离测试库用固定验收文本执行用户同一提示词，同时每秒查询上下文 API。`deepseek-v4-flash`，轮次 `14ea40b4-9312-4356-8add-1b0888952d77`，16:59:43～17:00:10，COMPLETED / 无错误，逐字口令正确；508 个持久事件以 done 结束，最终消息存在，没有发生数据库写锁错误。
- 真实模型调用了 search_context、read_context、read_context；第一次读取参数失败后自行纠正，最终读取成功，不能声称全程无工具错误。四次供应商请求合计输入 66325 / 输出 1537 Token（供应商报告，非估算）。结果 `03-stream-lock-real-result.json`，日志 `03-stream-lock-real.log`。隔离库 `.pytest-tmp-03-real-stream-d9dcc365` 保留证据，测试配置中的真实凭据已清空；用户配置未动。

## 剩余范围

这次取得真实 API/SQLite/Worker 与真实模型证据，尚未在更新后的真实 Tauri/WebView2 内再次操作；旧 sidecar 仍加载启动时的 Python 模块，需要从托盘退出并重启后复测。没有重新跑无关全量或重新 Code Review，先前全量失败不随此次回归通过而关闭。
