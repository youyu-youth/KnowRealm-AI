# 03 — 文档分片：PDF 页码与内容块路径贯通

**What to build:** 文档导入（PDF / DOCX / txt / md）解析完成后产出文档分片：PDF 逐页提取并保留页码（现状提取时页码被丢弃）、DOCX 与 txt/md 按内容块分片；分片可经 API 查询，引用定位可落到页码或块。转写文本的产出（transcripts.content）与现状逐字节一致，文档分片是并行新增的定位层。PPTX 维持现状不支持。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 01（四表结构与模型）。与 02 可并行。

**Status:** done

- [x] PDF 逐页提取：每页一个分片，page_no 填充；空页跳过不产生分片
- [x] DOCX 按内容块（段落 / 表格）分片、txt / md 按内容块分片，page_no 为 NULL；section_title 可空
- [x] 分片挂靠 record_file（record_file_id 填充，course_material_id 恒 NULL 满足 CHECK）；start_offset / end_offset 为相对该文档全文 content 的字符偏移，与 content 对得上
- [x] 分片查询 API：文档分片并入 02 端点或以姊妹端点提供（形态与 02 对齐；若 02 未先行则本票引入，两票合并方向以先落地者为准）
- [x] 既有文档导入链路测试全绿；新增分片断言：页码填充、块切分、sequence_no 顺序、offset 正确性、多格式（pdf/docx/txt/md）覆盖
- [x] 全套门禁绿（pytest --basetemp / ruff / pyright strict）

**实施备注（7633d74）：**

- 结构镜像票 02 句流机制：解析产出 `DocumentBlock`（PDF 页码 1 起、DOCX 段落/表格、txt/md 空行切段）→ writeback 落 `<job_id>.blocks.jsonl` 缓存 → finalizer 与 transcript 同事务写 `document_segments`，两条定稿路径（complete_source_job / _finalize_record_if_ready）均覆盖；旧缓存无块文件（升级瞬间 in-flight）按纯文本切段降级（page_no NULL）。
- 查询 API 取**姊妹端点** `GET /api/records/{record_id}/document-segments`（与 02 的 transcript/segments 形态对齐，两类分片 schema 不混一响应）；sequence_no 为记录内跨文件全局连续。
- **偏离说明：迁移 0019 的 `document_segments.course_id` 由 NOT NULL 改为可空**——收件箱文档导入（无课程）是一等场景（既有测试佐证），NOT NULL 下分片写不进去；0019 未发布、仅存于本分支，按「已发布迁移不可改」纪律字面就地修正。票 06 文档回写时请同步数据模型 §4.5 的 course_id 语义。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真机导入真实 PDF / DOCX / txt / md，解析、转写浏览与升级前行为一致（本票不改任何现有 UI；分片 UI 消费在票 05）
- [x] 开发数据目录若在本次改动前已应用过迁移 0019：需重建开发库（或手动重建 document_segments 表放开 course_id 非空），否则收件箱文档导入会触发 NOT NULL 约束错误——**已了结（agent 2026-09-09 只读核实）：开发库 user_version=14，从未应用 0019，条件不成立无需处理；下次启动新代码会按修正后的 0019 连同 0015~0018 正常补齐建表**
