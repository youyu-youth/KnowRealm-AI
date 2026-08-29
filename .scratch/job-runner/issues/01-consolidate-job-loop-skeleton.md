# 01 — 收敛六个 worker 的任务循环骨架为 JobRunner

**What to build:** 把 audio / summary / quiz / knowledge_point / todo / document 六个 worker 逐字复制的任务循环骨架（run 主循环 ×6、条件抢占 UPDATE ×7、recover_interrupted ×4、_fail ×4，约 900 行复制品）收敛为 `backend/app/services/job_runner.py` 的一个 JobRunner 深模块。每个 worker 缩成一份**声明式执行体描述**（候选查询 + 实体装载 + 领取校验 + 执行体 + 写回 + 失败结局 + 变体字段），组合式注入，不用模板子类。纯重构、行为冻结：现有 HTTP 级行为测试保持绿色且不改断言。政策依据 ADR-0012（已落盘）。

**Status:** done

## 协议（grilling 共识，实现须逐条保真）

- **领取**：runner 持领取事务外壳与抢占原语（select 候选 → 校验 → 条件 UPDATE `status PENDING→RUNNING, attempts+1` → rowcount==1 才算抢占，现状七份逐字重复的 15 行竞态核心只存在一份）；spec 声明候选查询与校验。结果三态：
  - `claimed(ctx)`——携带领取事务内装载的实体上下文；
  - `cancelled(reason)`——写 CANCELLED + `result_json={"reason": "PREREQUISITE_CHANGED"}`，**不 notify**（现状契约）;
  - `waiting(reason)`——幂等条件 UPDATE 标注 `waiting_reason`、不抢占、**不消耗 attempts**，reason 真变化（rowcount==1）才 notify（audio 专用槽）。
- **执行**：执行体收到上下文 dataclass + 注入依赖（model / graph / ffmpeg_path / asr_client）；LLM 与网络调用悬在领取事务与写回事务之间，事务外执行。
- **写回**：spec 自持业务写事务（quiz/kp/todo 候选批次、summary 版本链、document/audio 走 transcript_finalizer 锁内事务）；写回开头的 `_source_is_current` 二次复检为可选钩子，quiz/kp/todo 共享实现连同 `_summary_content`（×4）归一到 `services/summary_derivation.py`，消除三处资格判定漂移。
- **失败结局**：声明式钩子 + 共享默认三种——终态（LLM 四域，max_attempts=1 无自动重试）、固定 1s next_run_at（audio ASR）、指数退避（document）。document 两处公式不一致（recover 用 `2**attempts`、fail 用 `2**(attempts-1)`）**原样保真**并以代码注释记录，不在本次修复。
- **通知**：`RecordInvalidationNotifier` 的四个协议点（recover / 领取成功后 / 写回尾 / 失败尾）归 runner，全部在事务提交后发送、CANCELLED 静默；notifier 进入执行上下文，仅供 audio 域内中途事件（转写成败 / checkpoint / waiting 变化，rowcount 门控保真）。
- **恢复**：runner 持默认"复位 RUNNING→PENDING"+notify（四份同构归一）；document 声明带退避公式的覆盖版；启动时调用顺序不变。
- **停止与节奏**：`_stopped` Event + `stop()` 归 runner；`poll_interval`（LLM 四域 0.25s、文件两域 1s）为描述字段。
- **并发**：每 worker 一个 asyncio 任务；audio 单任务内领取依序双试 transcode→ASR；`ffmpeg_path is None` 时工厂不注册 audio；**禁止合并单循环**。
- **横切政策**：六份相同的横切一律归 runner，差异以钩子槽表达，执行体不得自带横切副本。

## Rider

- **main.py 注册表**：一张显式 worker 工厂表替代逐个局部变量与六层嵌套退出金字塔（main.py:193-215）；启动循环（recover + create_task）、退出逆序循环、`engine.dispose` 唯一 finally；不自注册。
- **测试工具**：仅收敛本次迁移触碰测试文件中的 `wait_for_*` 轮询 helper 与 FakeSummaryModel 副本，不做全仓清扫；runner 时钟可注入为正式构造参数；禁止新增对私有方法的 monkeypatch（`test_document_import.py:917` 对 `_claim_one` 的 patch 迁到 runner 正式接缝）；暂停槽仅当某 worker 迁移受阻表达不出时按需补。

## 迁移顺序（每步全绿后进下一步，各自成 commit）

1. `job_runner.py` + `summary_derivation.py` 落地，`todo_worker` 试点迁移
2. `quiz_worker` → `knowledge_point_worker`（同构对）
3. `summary_worker`（graph/HITL 执行体分离的自证）
4. `document_worker`（指数退避 + SQLITE_BUSY continue 分支保真）
5. `audio_worker`（双流水线 + waiting 三态 + checkpoint 保真）
6. main.py 注册表收口，六层金字塔删除

## 验收

- [x] 六个 worker 迁移完成，`job_runner.py` 是任务循环骨架唯一归属；run/抢占/recover/fail/stop 同构代码在 worker 文件中不复存在
- [x] 每步迁移后：后端全量测试、ruff check、ruff format --check、pyright 全绿；HTTP 级行为测试断言零修改
- [x] 领取三态（claimed / cancelled 静默 / waiting 不耗 attempts）与通知协议点（提交后时机、CANCELLED 静默）有测试覆盖
- [x] `_summary_content` / `_source_is_current` / PREREQUISITE_CHANGED 取消段收敛到共享模块，三处漂移风险消除
- [x] main.py 退出金字塔消失，worker 注册为显式表
- [x] document 两处 2^n 退避公式不一致以代码注释记录（不在本次修复）
- [x] `_claim_one` monkeypatch 测试迁到 runner 正式接缝，`# pyright: ignore[reportPrivateUsage]` 移除
