# 03 — 文档分片：PDF 页码与内容块路径贯通

**What to build:** 文档导入（PDF / DOCX / txt / md）解析完成后产出文档分片：PDF 逐页提取并保留页码（现状提取时页码被丢弃）、DOCX 与 txt/md 按内容块分片；分片可经 API 查询，引用定位可落到页码或块。转写文本的产出（transcripts.content）与现状逐字节一致，文档分片是并行新增的定位层。PPTX 维持现状不支持。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 01（四表结构与模型）。与 02 可并行。

**Status:** ready-for-agent

- [ ] PDF 逐页提取：每页一个分片，page_no 填充；空页跳过不产生分片
- [ ] DOCX 按内容块（段落 / 表格）分片、txt / md 按内容块分片，page_no 为 NULL；section_title 可空
- [ ] 分片挂靠 record_file（record_file_id 填充，course_material_id 恒 NULL 满足 CHECK）；start_offset / end_offset 为相对该文档全文 content 的字符偏移，与 content 对得上
- [ ] 分片查询 API：文档分片并入 02 端点或以姊妹端点提供（形态与 02 对齐；若 02 未先行则本票引入，两票合并方向以先落地者为准）
- [ ] 既有文档导入链路测试全绿；新增分片断言：页码填充、块切分、sequence_no 顺序、offset 正确性、多格式（pdf/docx/txt/md）覆盖
- [ ] 全套门禁绿（pytest --basetemp / ruff / pyright strict）
