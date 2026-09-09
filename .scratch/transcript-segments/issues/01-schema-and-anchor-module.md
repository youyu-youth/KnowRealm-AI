# 01 — 四表结构与 source_anchor 模块就位（prefactor）

**What to build:** 应用升级后数据库具备分片与锚点结构：新增迁移建立四张表——`transcript_segments`（转写分片）、`document_segments`（文档分片）、`source_anchors`（来源锚点）、`source_anchor_links`（锚点链接，多态）；转写/文档分片模型归 transcript 模块，来源锚点以独立模块提供唯一入口（service + 只读 API）。本票是 02~05 的数据地基（make the change easy, then make the easy change），锚点表本期零写入者、空表就位；表结构按数据模型 v2.3 §4.5 定稿，唯一修正是转写分片四个时间戳列允许 NULL（= 无时间轴来源，v2.4 语义，见 spec「来源时间轴」四项根决策）。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 迁移 0019 建四表：transcript_segments 索引 (record_id, sequence_no)、(file_id, file_start_ms)、(record_id, record_start_ms)，speaker 列建着恒 NULL 预留；document_segments CHECK（record_file_id 与 course_material_id 必须且只能一个非空，course_material 路径本期恒 NULL）；source_anchor_links 唯一约束 (resource_type, resource_id, source_anchor_id, relation_type)
- [x] 转写分片四时间戳列（record_start_ms / record_end_ms / file_start_ms / file_end_ms）允许 NULL；speaker、document_segments.page_no / section_title 可空
- [x] source_anchors 的 Audio/Document 来源「至少关联一个具体分片」约束落地（CHECK 落地：精确类型匹配——AUDIO_SEGMENT 必须挂 transcript_segment_id、DOCUMENT_SEGMENT 必须挂 document_segment_id，跨挂被拒；比数据模型 §10 字面「至少一个 segment 非空」更严，票 6 升 v2.4 时须同步标注此收紧）
- [x] source_anchor 独立模块：模型 + service + 按记录查询锚点列表的只读端点（空态正常响应）；模块 docstring 声明锚点唯一入口（对标 search 模块先例）
- [x] 全量 user_version 断言同步（11 个测试文件中 10 处硬编码 18→19；test_archive.py 为 supported_user_version() 动态断言无需改；导入归档版本上限走同一动态函数，自动生效零改动）与导入归档版本上限逻辑
- [x] 迁移测试：四表结构 / CHECK / 索引 / NULL 语义断言；全套门禁绿（pytest --basetemp / ruff / pyright strict）；openapi 导出与 api-types 因新只读端点重新生成、零漂移
