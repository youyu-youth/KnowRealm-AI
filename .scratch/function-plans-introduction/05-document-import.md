# 05 - 文档导入

> Wave: A ｜ PRD: §4.3.2（文档）/ §4.3.0 L5 ｜ 决策引用: #29 #44 #45 #54

## 功能描述 / 目标

课件 / 文档捕获（五级入口 L5）：跳过 ASR，解析直接产出 Transcript 进入 AI 管线，复用 04 建立的 worker 编排与状态机。

## 功能范围

**做**：
- 文档格式：PDF / DOCX / PPTX / TXT / MD（PyMuPDF / python-docx / python-pptx / 原生文本；OCR 不做）
- 解析结果写 Transcript（无音频文件，轻捕获直写）
- 一条记录可多段音频 + 多个文档混合关联（record_files sequence_no 定序，转写文本按序合并，#54）
- 已选课导入 → 直接 SUMMARY_PENDING 进总结管线；未选课 → 纯存储（NOTE，等同速记，手动升级，#29）
- 文档导入入口挂 02 快速捕获条

**不做**：
- OCR、网页剪藏（P2）、图片型 PDF 提示（仅提示不支持，不识别）

## 核心业务流程

选择文件（+可选课程）→ 经 API 落盘 files/ → 注册 record_files → CONTENT_PROCESSING（worker 解析）→ Transcript 落库 → 已选课自动触发 06 / 未选课停为 NOTE 等待升级

## 关键业务规则

- 英文文档 V1 正常处理、AI 输出中文（#45）
- 定序规则同 04：CONTENT_PROCESSING 开始后不可重排（#54）
- 解析失败 → FAILED 可重试；处理中删除竞态规则同 04
- 无体积硬限，磁盘剩余空间防呆规则同 04（#44）

## 前置依赖

- 04（复用 worker 编排 / 状态机 / record_files 定序 / SSE 状态推送）

## 验收标准（出口线）

- [ ] 导入 PDF → 详情页看到解析全文 → 已选课自动触发总结
- [ ] 同一记录混挂音频 + 文档，转写文本按导入顺序合并展示
- [ ] 未选课导入停为 NOTE，不消耗 AI 调用
- [ ] 损坏文件解析失败 → FAILED → 重试或删除
