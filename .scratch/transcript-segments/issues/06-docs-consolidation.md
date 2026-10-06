# 06 — 文档落盘收尾：数据模型 v2.4 升版与交叉引用同步

**What to build:** F1 全部落地后，权威文档反映已实施事实：数据模型文档升 v2.3→v2.4（四表标注已实施、时间戳 NULL 语义、变更记录行新增、文件重命名）；扩展设计文档 §7（F1）回写实施定案差异；PRD 等全部交叉引用同步。遵循文档惯例：评审定稿即升版并重命名、历史变更记录行是史实不改、改版本号须同步全部交叉引用（PRD / 技术栈 / GLOSSARY.md / 扩展设计文档头部）。

**Spec 参考:** 同目录 `../spec.md`（F1 两轮 grill 全部定案裁决、领域术语与测试缝隙；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 01、02、03、04、05（全部完成后回写「已实施」才真实）。

**Status:** done

- [x] 数据模型 v2.3→v2.4：git mv 重命名；§4.5 四表更新为已实施态（时间戳列 NULL 语义、document_segments course_material 路径预留未启用）；变更记录行新增（史实行不动）
- [x] 扩展设计文档 §7 回写：F1 已实施标注 + grill 定案差异（交付边界 B / anchor 空表就位 / 术语「来源时间轴」/ PPTX 维持不支持 / 音频回放独立票 convertFileSrc 方向）
- [x] 全库交叉引用同步：PRD、技术栈设计与审查、GLOSSARY.md（已更新的「片段」「来源时间轴」词条核对）、扩展文档头部版本引用；grep 无 v2.3 残留指向数据模型文档的引用
- [x] 工单回写：本目录 01~06 票状态与验收项逐条核对后置 done；docs: 提交（工单完结回写惯例）

**实施备注（本票为纯文档变更，随 docs: 提交落盘）：**

- v2.4 变更记录行 + §4.5 已实施标注覆盖票 01/03 全部偏离项：四时间戳列可空（NULL=无时间轴来源三场景）、document_segments.course_id 可空（收件箱一等场景）、course_material_id 预留无外键、source_anchors CHECK 收紧为精确类型匹配（§10 同步）、四表无 created_at/软删列。
- 扩展文档 §0 D9 与头部权威文档名、§40.3 A0 行、§40.4 第 1 步同步标注已实施；spec §API 帧的「mm:ss」补记 h:mm:ss 进位（07 补票交付事实）。
- 交叉引用同步范围：PRD v2.7 头部、技术栈 v4.5 §SQLite 行、GLOSSARY.md 头部、根 AGENTS.md 权威文档表、backend/AGENTS.md 迁移纪律（0018→0019、user_version 18→19、test_archive.py 动态断言说明）。grep 复核：权威文档零 v2.3 残留；`.scratch` 历史工单/spec 中的 v2.3 为当时定稿史实，按惯例不改。
