# 05 - 文档导入

> Wave: A ｜ PRD: §4.3.2（文档）/ §4.3.0 L5 ｜ 决策引用: #29 #44 #45 #54

## 功能描述 / 目标

课件 / 文档捕获（五级入口 L5）：跳过 ASR，解析直接产出 Transcript 进入 AI 管线；作为首个后台任务消费者，同步引入最小 worker、processing_jobs 与 UI 轮询入口。

## 功能范围

**做**：
- 文档格式：PDF / DOCX / PPTX / TXT / MD（PyMuPDF / python-docx / python-pptx / 原生文本；OCR 不做）
- 最小 sidecar asyncio worker、processing_jobs 技术任务态与处理中轮询；业务态不混写技术进度
- 解析结果写 Transcript（无音频文件，轻捕获直写）
- 一条记录可多段音频 + 多个文档混合关联（record_files sequence_no 定序，转写文本按序合并，#54）
- 已选课导入 → 直接 SUMMARY_PENDING 进总结管线；未选课 → 纯存储（NOTE，等同速记，手动升级，#29）
- 文档导入入口挂载 01 已提供的顶部快速捕获栏；创建后的 Record、状态与 Transcript 内容挂载复用 02 的列表和详情入口

**不做**：
- OCR、网页剪藏（P2）、图片型 PDF 提示（仅提示不支持，不识别）

## 核心业务流程

选择文件（+可选课程）→ 经 API 落盘 files/ → 注册 record_files 与 processing_jobs → CONTENT_PROCESSING（worker 解析，UI 轮询状态）→ Transcript 落库 → 已选课自动触发 06 / 未选课停为 NOTE 等待升级

## 关键业务规则

- 英文文档 V1 正常处理、AI 输出中文（#45）
- 定序规则同 04：CONTENT_PROCESSING 开始后不可重排（#54）
- 解析失败 → FAILED 可重试；处理中删除竞态规则同 04
- worker 每步写入前检查 `record.deleted_at`，发现软删即终止并丢弃产物（#54）
- 无体积硬限，磁盘剩余空间防呆规则同 04（#44）

## 前置依赖

- 02（复用 Record 表、列表、详情与软删除语义；本 plan 首次引入后台任务基础）

## 验收标准（出口线）

- [ ] processing_jobs 可查询文档解析任务；worker 推进任务与 Record 业务态，桌面轮询可见且不依赖 SSE
- [ ] 导入 PDF → 详情页看到解析全文 → 已选课自动触发总结
- [ ] 同一记录混挂音频 + 文档，转写文本按导入顺序合并展示
- [ ] 未选课导入停为 NOTE，不消耗 AI 调用
- [ ] 损坏文件解析失败 → FAILED → 重试或删除
- [ ] 删除处理中记录 → worker 停止且无后续产物入库
