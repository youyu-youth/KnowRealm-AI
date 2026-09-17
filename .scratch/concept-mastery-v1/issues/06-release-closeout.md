# 06 — 完成一体化验收与权威文档收口

**What to build:** 将 Concept Mastery 作为一次完整功能交付：所有自动化门禁、真实 Tauri 验收准备、架构决策、数据模型与项目交接信息一致反映当前代码，不保留示意 Mastery 或过期规划口径。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery; 03 — 从 Mastery 下钻到每条 Quiz Evidence; 04 — 让删除、归档、重启与算法升级保持 Mastery 正确; 05 — 在 Course Brain 中查看非侵入式 Mastery 状态.

**Status:** ready-for-agent

- [ ] 新增 ADR，记录验证性 Evidence 唯一改变 Mastery、确定性派生快照、与 Forgetting 分离以及拒绝多 Concept/历史猜测回填的理由。
- [ ] 数据模型升版并按仓库惯例重命名，标记 Quiz 主概念与 Mastery 表已实施，移除或更正 Concept Evidence 恒为空等过期描述。
- [ ] 功能基线、技术栈、扩展设计、领域词汇及全部交叉引用与实际代码一致，历史变更记录保持史实不改写。
- [ ] 项目进度文档更新为当前完成状态并保持 200 行以内，删除现有 Knowledge GPS/Mastery 仍为示意的过期说明。
- [ ] 全库检索确认章级模拟 Mastery、课程模拟掌握度及相关假数据不再被生产入口使用；无关示意功能不借机删除。
- [ ] 后端相关测试与全量 pytest、ruff、pyright、OpenAPI 契约检查通过，测试临时目录在完成后清理。
- [ ] 前端相关测试与稳定并发全量测试、lint、触及文件格式检查和 build 通过；不为无关历史格式债务扩大改动范围。
- [ ] 真实 Tauri/WebView2 验收清单覆盖亮色、暗色、窄窗口、零数据、数据不足、四类状态、Evidence 下钻和 Course Brain 标记；自动化结果不冒充真机证据。
- [ ] 用户真机验收项保持未代勾状态，交接中明确代码门禁、模拟渲染与真实桌面验证的证据边界。
