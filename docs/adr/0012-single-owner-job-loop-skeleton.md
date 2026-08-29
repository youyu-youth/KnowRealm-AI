# 任务循环骨架单一归属：JobRunner 与执行体描述

processing_jobs 表是队列，sidecar 进程内 asyncio 任务是消费者（fastapi.md 规则）。六个 worker（audio / summary / quiz / knowledge_point / todo / document）曾各自复制同一份任务循环骨架——run 主循环 ×6、条件抢占 UPDATE ×7、recover_interrupted ×4、_fail ×4 逐字重复，约 900 行复制品；骨架缺陷（抢占竞态、退出顺序、恢复语义）需修六遍，而 worker 之间真正变化的只有 job_type、领取校验与执行/写回体。决策：骨架单一归属 `services/job_runner.py` 的 JobRunner（组合式注入）；每个生成域缩成一份声明式执行体描述；相同横切（轮询、抢占、恢复、失败记账、停止、协议点通知）归 runner，差异以钩子槽表达，执行体不得自带横切副本。新生成域（模拟测试、复习资料等）一律写执行体描述，禁止复制骨架。实现工单见 `.scratch/job-runner/issues/01`。

## Considered Options

- 模板子类 WorkerBase——变体决策点固化为可覆盖方法，接口随变体增多而变宽，单个域的差异无法在一处整体阅读。
- 维持每功能复制骨架——rule-of-three 已违反两倍；Wave B 每个新生成域再引入约 150 行复制。
- 合并为单循环单任务——属行为变更（轮询节奏 0.25s/1s 混同、恢复语义合并），任务数不是设计目标。

## Consequences

- 新增生成域从约 370 行 worker 文件降到约 100–200 行执行体描述；骨架级缺陷修一处生效全部。
- 领取协议固定三态：claimed / cancelled（静默）/ waiting（标注不抢占、不消耗 attempts）。
- 协议点通知（recover、领取后、写回尾、失败尾）由 runner 持有并在事务提交后发送；CANCELLED 静默成为显式契约。
- 失败结局为声明式钩子 + 共享默认（终态 / 固定 1s / 指数退避）；document 两处 2^n 公式不一致被显式保真，修复须另立工单。
- 行为冻结基线：HTTP 级测试断言零修改是重构安全性的判据；claim 后暂停、时钟控制走 runner 正式接缝，禁止私有 monkeypatch。
