# Learner Memory 复用可治理业务事实，经 HITL 写入而不依赖 Agent 运行时存储

---
Status: accepted（2026-09-18，Learner Memory grill Q18-M、Q19~Q42 定稿）
---

KnowRealm-AI 需要跨会话使用稳定的学习偏好、目标与已验证学习状态，但普通聊天历史、LangGraph Checkpoint、DeepAgents Store 和向量 RAG 都不等于可信的长期学习者记忆。若自动从每轮聊天抽取“记忆”，会产生不可见推断、范围污染与外部模型隐私风险；若新建通用 `memories` 表，又会复制现有 Mastery、Misconception、Goal 与 `learner_preferences` 事实。

**决定**：

- **Learner Memory V1 是独立纵向能力，纳入资料库同一外部发布波次**，但不与 RAG 表或检索索引混存。RAG 回答“资料里有什么”，Learner Memory 回答“用户已确认的稳定偏好与学习状态是什么”。
- **长期事实复用业务表**：`learner_preferences` 是单例偏好事实表，保存用户显式偏好和经确认的观察偏好；Mastery、Misconception、Goal 继续留在各自表。`LearnerProfileService` 按任务聚合这些事实，生成限长、可重建的 Learner Context；不新建同义 `learner_profiles` 或通用 `memories` 表。
- **写入来源受限**：用户直接编辑可立即写入；结构化 Learning Evidence 或用户明确“记住”只产生 MEMORY 提案，确认后由领域 Service 写入。普通聊天不得静默抽取、自动强化或覆盖记忆；观察偏好不得覆盖用户显式偏好。
- **记忆可治理**：学习画像中的“AI 记忆”提供查看、编辑、删除与来源 / 置信信息；对话中以提案卡请求确认，不把记忆伪装成资料资产，也不增加资料库分类。
- **上下文最小化且严格分域**：全局显式偏好可跨课程使用；Mastery、Misconception、Goal 等状态按当前 Course / Record / LibraryItem 任务范围选择，ALL 也只注入完成当前任务所需的最小集合。回答界面必须能说明使用了哪些记忆。
- **运行时存储不是事实源**：`langgraph.db` 只存 Checkpoint / 运行态；DeepAgents Store、Filesystem Memory 与聊天消息不承载长期 Learner Memory。跨重启待审记忆提案落 `agent_proposals`，不依赖 Graph interrupt 持续挂起。
- **外发需单独同意**：本地查看、编辑和聚合不需联网；向外部 LLM 发送最小 Learner Context 前必须告知并取得同意，设置页提供长期记忆外发开关，更换模型供应商后重新确认。日志不得记录完整记忆正文。
- **可迁移、可离线**：全量导出 / 备份包含 `learner_preferences` 及相关业务事实；离线时记忆查看、编辑、删除与本地聚合继续可用，依赖 LLM 的建议明确降级。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. 业务事实表 + LearnerProfileService 聚合 + MEMORY 提案 HITL** | **采纳**——最少新状态，用户可见可纠正，能严格控制范围和外发 |
| B. 现在不上记忆，等完整 Learner Brain | 否决——跨会话个性化是本波次明确需求，且现有偏好 / Mastery 事实已能支撑最小闭环 |
| C. 通用 memories 表或向量记忆 | 否决——复制领域事实、难以删除纠正，且语义相似不等于事实有效 |
| D. DeepAgents Store / Filesystem Memory | 否决——适合 Agent 运行时持久化，不应替代产品业务事实与治理 UI |
| E. 每轮聊天自动总结为记忆 | 否决——噪声、隐私与未经授权写入风险高，违反 HITL 边界 |

## Consequences

- Learner Memory V1 不要求 sqlite-vec，也不依赖资料库索引；两者可在同一发布波次独立验收。
- 首版记忆不做开放式日记、任意文本知识或自动遗忘算法；需要新记忆类型时，先证明它不能由现有领域事实派生，再扩展明确 schema。
- 发布零容忍门禁包括：未经确认写入 / 修改记忆、跨 Course 注入状态、关闭外发后仍发送记忆、删除后仍被上下文使用。
