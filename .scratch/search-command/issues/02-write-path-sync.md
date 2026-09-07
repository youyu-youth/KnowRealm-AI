# 02 — 写路径同事务索引同步

**What to build:** 用户编辑任何可检索内容并保存后，新词立即可搜、旧词不再命中：三实体四类写路径——学习记录创建/改标题、转写落稿与编辑、知识点确认/编辑/重新生成、课程创建/改名——在同一业务事务内 upsert 索引行；业务写回滚时索引同步一并回滚。全部验收经既有 HTTP 端点完成，不新增对外 API。

**Blocked by:** 01（复用 search 模块索引 upsert 接口与索引表）。

**Status:** done

- [x] 经既有端点完成下列操作后新词立即可搜：改记录标题、保存转写编辑、确认/编辑知识点、重新生成知识点、创建/改名课程
- [x] 改名/编辑后旧词不再命中（转写编辑场景构造旧词失配用例）
- [x] 索引 upsert 与业务写在同一事务（同步失败业务写一并失败的构造用例）
- [x] 转写落稿（转写任务完成写入全文）后正文可搜
- [x] 上述全部有 pytest 覆盖，仅经既有端点操作并断言 /api/search 响应

**实现备注（2026-09-07，agent 交付）：**

- 挂点清单（11 处、均在校务写 flush 后、`session.begin()` 块内）：记录创建 5 条捕获路径（text_capture / audio_import / document_import / capture_batch 录音封口与批次导入）、转写落稿 2 处（finalizer 的 `finalize_record_if_ready` 与 `complete_source_job`）、转写编辑（record/service.update_transcript）、知识点手动新增/编辑/确认（kp service 三处）、知识点重新生成落 DRAFT（kp worker.writeback）、课程创建/更新（course service 两处，update 内挂点自动覆盖所有调用方含 hot_words）。软删/归档不碰索引行（查询期过滤，票 01 口径）。
- 验收口径说明：全仓核查确认不存在「学习记录改标题」端点（前端亦无调用），记录标题仅在创建时写入；本票按「创建时标题入索引」覆盖该项（5 条创建路径全部挂点并有测试），旧词失配用例按工单指定以转写编辑场景构造。若将来新增记录改名端点，在同一事务调 `upsert_record_index` 即可。
- 性能修正（评审发现的回归）：jieba 切词与正文长度线性，4 MiB 文档全文切词约 9 秒且同步阻塞事件循环，曾致 `test_server_process` 崩溃恢复用例 API ReadTimeout（stash 对照确认系本票挂点引入）。修复 = 索引正文限长前 30,000 字符（`_INDEX_BODY_LIMIT`，对齐 LLM 侧 `TRANSCRIPT_LIMIT` 量级）+ 切词移 `asyncio.to_thread`。**待用户裁决**：spec 原文为「body=转写全文」，截断后超长正文（约 5 小时以上转写或巨型文档导入）尾部词不可搜；若不接受可改异步索引方案，但需接受大文档落稿期间秒级卡顿或拆事务。
- 确认（confirm）挂点说明：确认不改检索内容（DRAFT→ACTIVE 均在查询过滤口径内），挂点属防御性显式补行——覆盖「候选生成于旧版本、未回填即确认」的异常态，幂等无害，并使「确认后可搜」不依赖 writeback 前置假设（测试以 SQL 抽走索引行后确认仍可搜直证）。
- 测试 8 例追加于 tests/test_search.py（全量 382 绿 / ruff / pyright strict 全绿）：文本捕获标题+正文、文档导入创建+落稿正文（真实 document worker 走 `complete_source_job`）、转写编辑新旧词、知识点手动新增/编辑新旧词、重新生成（fake 模型注入走真实 worker writeback）+确认补行、课程创建/改名/hot_words、同步失败回滚（monkeypatch upsert 抛错 → PATCH 500 → 内容未变且索引未更新）。音频 ASR 落稿与文档共用 `complete_source_job` 同一挂点，ASR 链路既有测试均 mock 供应商，未单列端点级用例。
- 双轴 code-review：标准轴零硬违规（挂点形状 11 处重复属「显式事务边界调用 vs after_flush 事件钩子」的既定取舍）；规格轴除上述两项待裁决外无缺失。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真实数据目录上编辑转写/改标题/确认知识点后，命令面板立刻搜到新内容
