# 02 — ASR 管道接住句子时间戳：音频路径贯通

**What to build:** 新导入音频转写完成后，课堂自动获得句级来源时间轴：腾讯 ASR 返回的句子级起止时间戳不再在客户端边界丢弃，随转写定稿写入转写分片表；多段录音按文件顺序拼接出课堂时间轴（record_start_ms = 前序文件 duration_ms 累加，非真实墙钟）；版本升级瞬间的在途转写任务按降级方式合并完成（不重跑、不重复计费、不报错）。新增分片查询端点，转写完成后即可经 API 读到带时间戳的句级分片——本票以「音频导入 → 转写完成 → API 返回句级时间轴」为端到端验收路径。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 01（四表结构与模型）。

**Status:** done

- [x] 腾讯 ASR 客户端解析 ResultDetail 中每句的起止时间戳，ASR 任务结构增加结构化句子列表；既有错误码映射与计费/重试行为不变
- [x] chunk 文本缓存从纯 txt 改 JSONL（每句 text + 起止时间）；ASR checkpoint 结构兼容扩展（新字段可选，chunks[i].sentences_path；旧 checkpoint 的 text_path 兼容读取）
- [x] 转写定稿（finalizer）合并各文件句子流写入 transcript_segments：sequence_no 全记录连续；record_start_ms 按文件 sequence_no 顺序累加 duration_ms；file_start_ms 为句内时间；`transcripts.content` 的合并拼接结果与现状逐字节一致（content 链路走原有 .txt 中转零改动，句子流平行新增 JSONL；空句保留在 content、不进分片）
- [x] in-flight 降级：升级瞬间的旧 checkpoint / 纯 txt 缓存按纯文本合并为无时间戳分片（不重跑、不报错、不重复腾讯计费）——两场景已覆盖：chunk 级旧 checkpoint 恢复（audio_worker 降级读 txt 行拆）、升级前已 SUCCEEDED 任务重启定稿（finalizer `_read_source` 行拆）
- [x] `GET /api/records/{record_id}/transcript/segments`：一次返回全部分片（不分页）、无分片记录空态正常；沿用既有 record 级访问门禁（软删 404 / ARCHIVED 课程不拦，与 transcript 端点同口径）
- [x] api-types 重新生成；fake ASR client 全链路测试覆盖：单/多文件时间轴连续性与时间戳正确性、JSONL 落盘、降级合并路径；只断言 API 响应与落库行为，不测内部函数
- [x] 全套门禁绿（pytest --basetemp / ruff / pyright strict）

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真机导入一段音频，转写完成后课堂详情（或直接 curl 分片端点）可见带时间戳的句级分片
