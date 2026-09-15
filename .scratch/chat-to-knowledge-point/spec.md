# 对话转学习资产 V1（对话转知识点：AI 回答保存 + 锚点溯源）

Status: done

## Problem Statement

B2 之后 AI 对话能跨记录检索作答，但回答「用完即走」——聊明白的内容无法沉淀为学习资产，「问 → 懂 → 沉淀」闭环缺最后一环（基线 Phase 2 已定项「对话转学习资产」，基线 :261）。同时 `source_anchors` / `source_anchor_links` 两表自 F1 交付以来零写入者，锚点溯源体系只有地基没有数据。

## Solution

1. **保存端点**：`POST /api/chat-sessions/{sid}/messages/{mid}/knowledge-points`——把一条 AI 回答保存为目标记录的知识点；前置校验（会话存活 404 / 消息属该会话 404 / role=ASSISTANT 409）。
2. **同事务四写**：知识点（走 `KnowledgePointService`，ACTIVE）+ 搜索索引 + `CHAT_MESSAGE` 锚点（锚点体系首个写入者）+ `KNOWLEDGE_POINT/PRIMARY` 链接；事务由 agent 路由编排层统一管理（校验查询触发 autobegin，Service 内再 begin 会撞已开事务）。
3. **不污染学习证据**：不调 `write_learning_event`（AI 辅助沉淀 ≠ 用户已掌握，AI 自述不是 Evidence 红线）。
4. **追溯读**：`KnowledgePointOut` 增可选 `chat_source: {chat_session_id}`（read 经 链接 × 锚点 × chat_messages 三表 JOIN 派生）；不回查会话软删（历史事实保留，跳转后自然处理失效态）。
5. **前端全范围**：所有 scope 会话的 AI 回答带「保存为知识点」入口；目标记录选择器（record-options 中已归类且有转写者；RECORD 会话默认挂载记录）；detail 预填聚焦摘要（首段去 markdown + 带 [n] 引用句去角标去重，纯函数）；知识点列表「源自 AI 对话」徽章跳回原会话。
6. **零迁移**：四张相关表全部现成，user_version 断言零改动。

## User Stories

1. As an 对话用户, I want to 把有价值的 AI 回答一键保存为知识点并挂到目标记录, so that 聊明白的内容不再用完即走。
2. As an 对话用户, I want to 保存时预填回答的聚焦摘要并可编辑名称/详情/标签/重要度, so that 确认成本最低且内容可修正。
3. As an 学习者, I want to 知识点列表看到「源自 AI 对话」徽章并可跳回原会话, so that 沉淀的内容可追溯到当时的提问、回答与引用。
4. As an 用户, I want to 保存的知识点与手工新增行为一致（可编辑/删除/进搜索）, so that 资产管理不出现第二套规则。

## 决策记录（用户拍板）

- V1 范围：**全 scope + 目标记录选择器**（非 RECORD-only 缩小版）。
- 追溯标识：**纳入 V1**（徽章 + 跳回会话，非仅落库）。
- detail 预填：**聚焦摘要**（首段 + 引用句，非全文非留空）。
- 目标记录无课程：409 复用既有码 `RECORD_COURSE_MISSING`（不新造码）。
- 新错误码：`CHAT_MESSAGE_NOT_FOUND`(404) / `CHAT_MESSAGE_NOT_ASSISTANT`(409)。

## Out of Scope（V1.1+）

- 自然语言「把刚才内容保存下来」（先按钮验证需求与数据语义）。
- 生成习题 / 总结 / Todo / 卡片等其它资产类型。
- 片段级锚点偏移（当前锚点 = 整条消息）。
- 保存产生学习事件（须 P4 结构化设计，防 AI 自述变证据）。
