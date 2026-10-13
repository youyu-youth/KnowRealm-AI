# 03 复盘改进实施

实施基点 `8025428`，仅测试工具、测试夹具、CI 与验收文档。四项建议均由用户批准；没有改业务代码、AGENTS、rules、用户级技能或记忆，也没有再次 Code Review。

## 落地

1. `backend/scripts/run_tests.py` 为本地与 CI 共用入口，复用 pytest/Vitest，不增加依赖。`all` 顺序执行前后端；前端单 worker，失败码传播且普通失败后仍执行下一套，超时/中断停止。最终验收与基点比较使用相同条件。
2. 每次独立日志目录保存完整命令、提交/脏工作区、PID、时间、时限、退出码及状态；后端详细进度、慢用例耗时、120 秒线程栈诊断，stdout 不缓冲。默认每套上限一小时；超时终止本次进程树并返回 124，用户中断返回 130，不能把缺少结束记录写成通过。CI 两个 job 在失败后也保存日志与结果，保留七天，不上传 basetemp 数据库。
3. 既有摘要测试增加 `assert_compaction_fixture`，提交前经生产 API 估算完整输入，断言工具定义、压缩阈值和能否容纳原输入；变化报告实际输入、预算与工具成本。没有再调窗口数值、放宽等待时间或替换原边界/次数/恢复断言。
4. `validation.md` 与 `issue-tracker.md` 给出开工时的完整验证路径及证据要求；03 增加 [桌面操作清单](03-desktop-acceptance.md) 与 [固定长文本](fixtures/03-long-message.txt)，链接回原工单。实际生产路径覆盖原消息/摘要和网页裁剪前快照，明确外部替身边界。所有人工条目保持 `NOT_RUN`，未触发不能算通过。

## 验证

- `uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_test_runner.py tests/test_conversation_compaction.py --timeout 600`：37 项通过（当时运行器 8 项 + 原摘要 29 项），176.91 秒；结果 `.pytest-tmp-runs/20261013T081714Z-48388803/backend/`。
- 追加线程栈诊断自检后，`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_test_runner.py --timeout 120`：运行器最终 9 项通过，13.52 秒；结果 `.pytest-tmp-runs/20261013T081950Z-e4052860/backend/`。真实临时进程验证成功/失败码、超时后子进程消失、启动失败；真实 pytest 的慢用例打印线程栈后仍通过。`all` 顺序/失败传播和参数拒绝为命令接缝自检，不冒充两套全量通过。
- 前端同入口 `frontend src/features/chat/toolIcons.test.ts src/i18n/locales.test.ts --timeout 120`：5 项通过（初次 20.89 秒，最终 UTF-8 输出复跑 12.65 秒）；最终结果 `.pytest-tmp-runs/20261013T082149Z-217c2e56/frontend/`。
- `scripts/check-changed.ps1`：触及 Ruff、格式、Pyright 0 错误通过（`03-retro-gates.log`）。工作流 YAML 解析及共用命令/诊断上传结构断言通过；上传 Action 固定提交及输入项核对官方 `action.yml`。
- 固定文本超过 5000 字符，独特首/中/末标记和两处重复短句；只准备数据，没有发送真实模型请求或导入用户资料。

## 边界

没有重新运行业务全量；本次仅改变执行方式和测试前提，既有全量失败记录保留，不豁免失败。远端 GitHub Actions、实际 Artifact 上传、真实模型/Tauri/Windows 缩放未执行；人工清单不是验收结果。

本次执行结果目录与 basetemp 保留为本地证据，不纳入提交。此前已被拒绝清理的预览文件及用户原有基点 worktree 保留，未再次尝试删除。
