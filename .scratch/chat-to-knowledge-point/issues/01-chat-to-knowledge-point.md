# 01 — 对话转学习资产 V1 全栈闭环：AI 回答保存为知识点 + 锚点溯源

**What to build:** AI 回答可被用户确认后保存为真实知识点（单票全栈，闭环不拆票）：新端点经 `KnowledgePointService.create_from_chat` 在**同一事务**写知识点 + 搜索索引 + `CHAT_MESSAGE` 锚点（锚点体系首个写入者）+ `KNOWLEDGE_POINT/PRIMARY` 链接；不发学习事件（不污染证据）。前端全 scope 会话的 AI 回答带「保存为知识点」入口 → 目标记录选择器 + 预填聚焦摘要表单 → 保存成功 Toast；知识点列表「源自 AI 对话」徽章跳回原会话。零迁移（四表现成）。

**Blocked by:** None.

**Status:** done

**后端**

- [x] `ChatKnowledgePointSaveRequest(KnowledgePointWriteRequest)`：继承四字段校验，显式 `strict=False`（pydantic config 合并语义，不写则继承 True，UUID 不吃 JSON 字符串）+ `target_record_id: UUID`
- [x] `ChatSessionService.get_message()`：会话存活（404 复用 CHAT_SESSION_NOT_FOUND）/ 消息属该会话（404 CHAT_MESSAGE_NOT_FOUND）/ role=ASSISTANT（409 CHAT_MESSAGE_NOT_ASSISTANT）
- [x] `SourceAnchorService.create_chat_message_anchor()` + `link_resource()`：锚点模块首批写入函数，无独立事务（调用方事务包住，对齐 learning.events 同事务红线）；Literal 约束 resource/relation 值域
- [x] `KnowledgePointService.create_from_chat()`：`_get_record`（目标记录无课程 409 复用 RECORD_COURSE_MISSING）→ `_new_item`（ACTIVE/batch NULL）→ flush → 搜索索引 → 锚点 + 链接；**无独立事务**（agent 路由编排层统一 begin——校验查询会 autobegin，Service 内再 begin 撞已开事务，事务由编排方管理）
- [x] 路由 `POST /api/chat-sessions/{sid}/messages/{mid}/knowledge-points`：`async with session.begin():` 包校验+写入，事务后 record_notifier 通知（对齐 KP 路由模式）；201 返回 KnowledgePointOut
- [x] `KnowledgePointOut` 增可选 `chat_source: {chat_session_id}`；`read()` 经 链接×锚点×chat_messages JOIN 批量填充（不回查会话软删——徽章表达历史事实，跳转后自然处理失效态）；其它出口默认 None
- [x] 测试 `tests/test_chat_knowledge_point_save.py` 9 用例：成功主路径（KP/锚点/链接/事件 0/索引同事务）、read 填充 chat_source（保存有/手工无）、FREE 会话任选记录、404×3+409（USER 消息/会话软删/无课程目标）、重复保存两套行无 UNIQUE 冲突、422 校验、锚点链接失败全回滚（monkeypatch）

**前端**

- [x] api-types 重新生成（新端点 + ChatKnowledgePointSaveRequest + KnowledgePointOut.chat_source）
- [x] `chatApi.saveKnowledgePoint(sessionId, messageId, body)`；类型经 `@knowrealm/api-types`
- [x] `buildSaveDraft` 纯函数（首段去 markdown 标记 + 跳过代码块 + 带 [n] 句子去角标去重 + 截断 ≤2000）+ 4 用例单测
- [x] `SaveKnowledgePointDialog`：目标记录 Select（懒查询 record-options `enabled: open`，过滤未归类/无转写；RECORD 会话默认挂载记录经渲染期派生重置）+ 复用导出的 `KnowledgePointItemForm`（key 绑消息重挂载刷新预填）+ 未选记录提交拦截提示 + 成功 Toast/知识点缓存失效
- [x] `ChatMessageList`：ASSISTANT 行加轻量「保存为知识点」按钮（messages 内回答均已落库，无流式歧义）；Dialog 挂载行内；`ChatConversationView`/`ChatWorkspace` 透传 sessionId + recordId
- [x] `KnowledgePointPanel`：导出 `KnowledgePointItemForm`/`KnowledgePointValues` 供 chat 域复用；行内「源自 AI 对话」徽章（chat_source 非空）跳 `/chat/$sessionId`
- [x] i18n：`chat.saveKp.*` 9 key + `record.detail.knowledgePoints.chatSourceBadge/Title` + 错误码表 CHAT_MESSAGE_NOT_FOUND/NOT_ASSISTANT（zh/en 同步）
- [x] 交互测试 2 用例（chat.test.tsx）：RECORD 会话保存全链路（默认目标/预填草稿/请求体断言/Toast）、FREE 未选记录拦截提示

**门禁与文档**

- [x] 后端：pytest 497 绿（--basetemp=.pytest-tmp）/ ruff check+format / pyright strict / openapi 重新导出生成
- [x] 前端：`pnpm test -- --maxWorkers=4` 446 用例（TodoPanel 1 例为既有间歇抖动、单跑绿）/ lint / 触及文件 Prettier / build 全绿
- [x] 错误码清单 +2（CHAT_MESSAGE_NOT_ASSISTANT/CHAT_MESSAGE_NOT_FOUND）+ RECORD_COURSE_MISSING 域补 knowledge_point；扩展文档 §40.3 B6 行 + §40.4 更新；PROJECT_PROGRESS 回写（含删除「learning_events 零消费者」过期行）
- [x] 提交分次：`feat(backend): 实现对话转知识点端点与锚点写入（对话转资产 V1）` + `feat(desktop): 接线保存知识点对话框与来源徽章（对话转资产 V1）` + `docs: 回写对话转资产 V1 交付结论`

**用户真机验收（不代勾）：** 真实会话中问出带引用的回答 → 点「保存为知识点」→ 选目标记录、确认预填内容 → 保存成功 Toast；打开目标记录的知识点 Tab 看到新知识点 + 「源自 AI 对话」徽章，点击回到原会话；重启应用后知识点与徽章仍在；全局搜索能搜到该知识点；对收件箱（未归类）记录保存时目标列表不含它；亮/暗两态与 zh/en 切换正常。
