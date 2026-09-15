# CB-12 — 全链路验收与文档收尾

**What to build:** 按 plan §十发布门禁逐项核验 + 全部文档同步。agent 侧验证止于自动化门禁，真机项单列用户清单不代勾。

**Blocked by:** CB-11。

**Status:** todo

**自动化验收**

- [ ] 多来源课程首次构建（KP+Transcript+Document 共同产候选）
- [ ] Candidate 确认/合并/忽略闭环；正式 Concept 不被重建覆盖（重跑断言）
- [ ] Record 删除与课程移动后来源/计数/图谱失效正确
- [ ] Source Anchor 时间/页码/对话跳转数据面正确
- [ ] 无 LLM Key 降级（等待态可浏览可手动维护）；LLM 构建失败恢复（旧图谱完好）
- [ ] B2 跨记录问答概念增强；"讲过几次 X"occurrences 去重 Record 计数
- [ ] Learning Evidence 零污染（learning_events/learning_evidence 零新行）
- [ ] Course Brain 页面无 Mock（grep courseDetailInsights 零残留）
- [ ] CB-01 结论归档 + sqlite-vec 口径明确

**文档同步**

- [ ] 数据模型 v2.7→v2.8（§4.6 标已实施 + 部分唯一索引论断更正 + 45 张表口径）并全库交叉引用同步（PRD/技术栈/CONTEXT/扩展文档头部）
- [ ] PRD v2.7 决策表/阶段表 F4 相关行更新；扩展文档 §40.3/§40.4 序列回写（F4 提前实施事实）
- [ ] `docs/后端错误码清单.md` 新码入册；CONTEXT.md 词条已随 CB-00 落
- [ ] PROJECT_PROGRESS.md 回写（≤200 行，删除被 F4 取代的"下一步候选"行）
- [ ] OpenAPI 类型最终 regenerate + `--check` 零 diff

**门禁**

- [ ] 后端四门禁 + 前端四门禁全绿；.pytest-tmp 删除
- [ ] 提交：`docs: 回写 F4 Course Brain V1 交付结论`

**用户真机验收（不代勾）**：多来源课程首次构建全程；候选审核（重命名/合并/忽略）；来源跳转（时间定位/页码/Chat 徽章）；课程对话问"讲过几次 X"核对次数与来源；无 Key 状态浏览与手动创建；重建后人工确认内容不被覆盖；亮/暗/窄窗/减少动效；zh/en 切换；真实语料检索评测（CB-01 口径补真）。
