# 03 — 统一入库与网页剪藏闭环

**What to build:** 「添加资料」统一入口支持网页 URL、本地文件与纯文本三类入库；网页经受限抓取 + trafilatura 正文提取保存净化快照，失败明确提示并降级手动粘贴；导入立即创建可见条目并显示确定性处理状态（解析中/可检索/失败+重试）；同内容哈希重复导入提示「打开已有/仍然保留」；成功处理的内容进入分片与检索索引、在工作台显示 RAG 可用性。

**Blocked by:** 02 — Schema、存量回填与基础工作台.

**Status:** ready-for-agent

- [ ] 统一入库入口 `ingest(request) -> LibraryItem + ProcessingJob`：路由层按 URL/文件/文本判别请求；新外部文件复制到数据目录后再处理（路径规范化并验证位于授权目录内）
- [ ] WebClipAdapter：httpx 受限抓取——仅 HTTP(S)、阻止 loopback/私网/链路本地/云元数据地址、每次重定向后重新解析校验（防 SSRF/DNS rebinding）、限制响应体与解压后大小/重定向次数/连接读取超时/Content-Type 白名单；以原始 bytes 做编码识别后交 trafilatura（>=2.2,<3 锁定）抽取正文与元数据
- [ ] 保存净化后的 Markdown/纯文本正文快照与来源元数据（fetched_at、判别校验的 metadata_json + schema_version）；不保存、不执行、不渲染原始 HTML
- [ ] 提取为空、过短、重复行过多等垃圾正文判定失败 → 明确错误信息 + 手动粘贴正文降级路径闭环；登录墙/网络不可达不重试轰炸
- [ ] FileAdapter 与 TEXT 请求复用现有导入校验、解析与分片管线；Segment 事实与检索索引同事务写入；处理状态从 Job/Segment 派生展示，无无限 spinner
- [ ] 同 content_hash 重复导入提示「打开已有条目 / 仍然保留」，不静默合并（服务端检测 + 最小 UI 交互）
- [ ] SSRF 防护与重定向重校验、垃圾正文降级、编码识别全部走注入的 fake transport 测试（不发真实网络）；重复导入 HTTP 级测试；trafilatura 新依赖入锁
- [ ] 「用系统浏览器打开 URL」「在系统资源管理器中显示本地文件」入口；zh/en 文案同步

## 备注

- ExistingCaptureAdapter（存量映射）不属本票——已随 02 的 LIBRARY_BACKFILL 落地。
- BookAdapter 待 `ai-summary/03` 完成后另开票，不在本波次。
