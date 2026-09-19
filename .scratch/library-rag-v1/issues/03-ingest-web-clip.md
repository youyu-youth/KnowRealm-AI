# 03 — 统一入库与网页剪藏闭环

**What to build:** 「添加资料」统一入口支持网页 URL、本地文件与纯文本三类入库；网页经受限抓取 + trafilatura 正文提取保存净化快照，失败明确提示并降级手动粘贴；导入立即创建可见条目并显示确定性处理状态（解析中/可检索/失败+重试）；同内容哈希重复导入提示「打开已有/仍然保留」；成功处理的内容进入分片与检索索引、在工作台显示 RAG 可用性。

**Blocked by:** 02 — Schema、存量回填与基础工作台.

**Status:** done（2026-09-19）

- [x] 统一入库入口：`POST /api/library/ingest`（JSON，web/text 判别）+ `POST /api/library/ingest/file`（multipart）→ `capture/ingest.py` LibraryIngestService 三路适配（服务落 capture 域=法定依赖方向 capture→下游，路由挂 library 域）；文件复用 document_import 的扩展名校验/临时落盘（cache/imports → os.replace 进 files/{record_id}/，磁盘空间预检，最终路径恒在数据目录 files/ 授权树内）；响应 202 = LibraryItemOut（availability 派生）+ ProcessingJobOut|null（web=WEB_FETCH max_attempts=1、file=DOCUMENT_PARSE、text 无 Job）
- [x] WebClipAdapter：`capture/web_clip.py`——字面 URL 校验（ingest 预检+每跳重定向共用）+ GuardedNetworkBackend 传输层 DNS guard（每次连接 getaddrinfo→校验全部候选 IP→直连已校验 IP 钉住解析，TLS SNI 走上层域名=httpcore 连接层天然解耦，无 rebinding 窗口；云元数据 169.254.169.254 由 is_link_local 覆盖）；手动跟随重定向（每跳重校验、上限 5 跳）、流式读取限解压后 5 MiB、连接 10s/读取 20s 超时、Content-Type 白名单（text/html、application/xhtml+xml）；编码识别=meta charset 声明优先（GBK 系字节范围重叠 sniff 易误判）+ charset_normalizer 候选兜底，trafilatura==2.2.0 入锁（>=2.2,<3）；生产 transport 环境有代理时尊重系统代理（对齐 B1 trust_env 语义），直连走 guard 池
- [x] 净化快照：web_fetch_worker 写回时 cache/webclips 临时写+fsync+os.replace 进 files/{record_id}/{job_id}.md（随全量导出 files/** 走）；条目更新 title（页面标题）/content_hash（正文哈希）/fetched_at/local_path/mime=text·markdown/file_size/metadata_json（kind:url:title:author:date:description:sitename 判别字段）+schema_version=1；原始 HTML 只进 extract_clip 函数栈不出模块，零持久化零渲染
- [x] 垃圾正文判定（<200 字符/非空行去重占比>0.8/净化正文>1 MiB/编码不可识别 → WEB_FETCH_EXTRACT_FAILED）；WEB_FETCH max_attempts=1 一次性终态不自动重试（登录墙/不可达不轰炸），Record 同步置 FAILED；降级闭环=详情端点透出 failed_error_code（解析链最新 FAILED 任务稳定码）→ 检查器失败态给「手动粘贴正文」（对话框 TEXT 标签预填 origin_uri+title）与「重新导入」（WEB 预填 URL）；通用 retry 端点（复用原 Job）按 contract §2.3 归工单 05
- [x] FILE 复用 document_import 全链（校验/落盘/DOCUMENT_PARSE Job），解析分片 finalize 由既有 document_worker 零改动承接；TEXT 复用 text_capture 校验（normalize/1 MiB 上限/首行标题）+Transcript 落库；WEB 写回单事务=Job SUCCEEDED+Record 状态推进（有课程 SUMMARY_PENDING+总结 best-effort 入队/无课程 NOTE）+Transcript+DocumentSegments（library_item_id 直挂=0026 XOR 另一分支首个写入者，blocks_from_plain_text 分块）+search_index/segment_search_index 同事务；三路同事务建 library_item_records 链接→LIBRARY_BACKFILL 差集扫描天然跳过（幂等测试断言）；处理状态=既有 availability 派生+前端列表 PROCESSING 存在时 2s 轮询、终态即停
- [x] 判重：服务端查未软删同 hash（web=规范化 URL 哈希占位、抓取成功后更新为正文哈希）→ 409 LIBRARY_ITEM_DUPLICATE_CONTENT + params.existing_item_id；allow_duplicate=true 放行双份；前端对话框内联「打开已有条目（选中并关闭）/仍然保留（allow_duplicate 重发）」
- [x] 测试：tests/test_web_clip.py 29 例（受限 URL 参数化×10/重定向重校验/安全跟随/次数超限/体积超限/Content-Type×3/HTTP 错误×2/GBK 编码/不可解码/登录墙短正文/重复行 spam/元数据字段/DNS guard 私网拒绝+公网 IP 钉住——全 fake transport+getaddrinfo 打桩，零真实网络）+ tests/test_library_ingest.py 12 例（text 202/判重 409→allow_duplicate/空正文/超限 422、web 无效与私网 422、file 真实 document_worker 闭环轮询至 RETRIEVABLE+快照落盘、web 闭环 fake adapter 全断言、有课程 SUMMARY_PENDING、失败 FAILED+错误码、URL 判重、入库-回填幂等）；trafilatura==2.2.0 入 uv.lock
- [x] 检查器操作行：origin_uri→openWebUrl（系统浏览器，B1 既有封装）；local_path→getDataDirectory+revealItemInDir（权限 opener:allow-reveal-item-in-dir 已入 capabilities）；zh/en 各 +36 键（ingest 子树/inspector 五键/errors 六码 HTTP 级）同步、防线通过

## 备注

- ExistingCaptureAdapter（存量映射）不属本票——已随 02 的 LIBRARY_BACKFILL 落地。
- BookAdapter 待 `ai-summary/03` 完成后另开票，不在本波次。
- 失败重试（复用原 Job attempts 归零）与 refetch/重建索引按 contract §2.3 归工单 05；03 的失败闭环 = failed_error_code 透出 + 重新导入（WEB 预填 URL）+ 手动粘贴降级。
- Record.capture_type：WEB 剪藏=CLIP（backfill 防御性映射预留位）、TEXT=PASTE、FILE=DOCUMENT_IMPORT——与 02 backfill 映射完全同构。
- ProcessingJob ORM 补 library_item_id 列映射（0026 DDL 有列但 02 未映射 ORM）；document_import 的 `_copy_upload`/`_remove_import_file` 公共化（pyright strict 跨模块私有拦截），test_document_cleanup monkeypatch 名同步。
- HTTP 错误码 WEB_FETCH_INVALID_URL/BLOCKED_URL（422，ingest 同步预检）入错误码清单；WEB_FETCH_CONTENT_TOO_LARGE/UNSUPPORTED_CONTENT_TYPE/UNREACHABLE/EXTRACT_FAILED 仅 job 域（ProcessingJobErrorCode，经详情 failed_error_code 透出前端翻译），清单「不入码表范围」补说明。
- 同仓并行 04 会话同时在写 agent 域与 LibraryPage「AI 解读」：03 提交经 index 版本剔除 04 半成品（LibraryPage.tsx/zh/en 三文件 hunk 级隔离）；api-types 生成物整体提交（含 04 后端已落的 chat scope schema——前端编译需要，后端代码随 04 提交后 openapi --check 在 07 收口统一校验）。
- 坑：httpx 0.28 AsyncHTTPTransport 无 backend 参数（经子类替换 httpcore.AsyncConnectionPool(network_backend=…)）；trafilatura 2.2 extract_metadata 恒返回 Document（None 检查是多余的）；charset_normalizer 对 GBK 短文本误判 cp949（meta charset 声明优先解决）；jsdom FormData 与 Node fetch 不兼容（multipart 断言放宽，形状由后端 HTTP 级验证）；对话框常挂载导致 useState(initial) 只在首挂载生效（open 翻转 effect 同步初始化）。

## 双轴 code-review 修复（2026-09-19，随 fix 提交）

- **[Spec-真缺陷] WEB 条目 hash 判重**：原实现抓取成功后把 content_hash 改写为正文哈希 → 同 URL 成功后再导入会静默建第二条。修为 hash 恒为 URL 哈希（判重锚），正文哈希记入 metadata_json.content_hash；FAILED 条目重新导入自然命中「打开已有（看到失败态）/仍然保留（重新抓取）」闭环。REFETCH 仍归 05。
- **[Spec/Standards-安全] 代理路径 SSRF 盲区**：原实现检测到代理环境变量即 trust_env 直连（guard 完全旁路）。修为每跳统一做目标域名解析预检（assert_resolves_public：解析结果须全部公网，解析失败放行交由连接路径报 UNREACHABLE），直连路径仍叠 guard 钉住。测试机 DNS 污染（example.com 解析受限地址）顺带暴露 fetch 测试依赖真实 DNS——全部打桩（零真实网络契约含 DNS）。备案进 contract 03 实施记录④。
- **[Standards-硬违规] Tauri 封装**：revealItemInDir/getDataDirectory 从 LibraryPage 下沉 services/tauri/libraryFiles.ts（revealLibrarySnapshot），对齐 desktop-tauri.md §1。
- **[Standards] recover_running 复用 mark_failed**（替代手写终态字段）。
- **备案不修**：LIMIT_EXCEEDED 1 MiB 口径（30k 属 plan18 未决+索引层限长，contract 03 记录①）；TEXT 无分片（与既有 PASTE 管线一致，复用优先；04 检索有 transcript 兜底）；capture⇄library 包级引用（02 先例，文件级无环）；AddLibraryItemDialog 160 行 JSX（贴上限不拆）；role="PRIMARY" 裸串（02 先例）。

## 用户真机验收清单（不代勾）

> 启动：`pnpm --filter @knowrealm/desktop tauri dev`（壳自动拉 sidecar）。检查器中若出现「AI 解读」按钮（Sparkles 图标）为并行 04 会话在制品，不在本票验收范围；chat 页异常同理。

- [ ] 三路入库：/library 顶部「添加资料」→ 网页/文件/文本三标签切换正常
- [ ] 文本：粘贴正文（可选标题/课程）→ 列表立即出现且「可检索」，检查器预览有正文
- [ ] 网页：正常文章 URL → 「解析中」数秒转「可检索」，标题=页面标题，检查器含来源 URL/抓取时间/快照路径/分片数≥1
- [ ] 文件：TXT/MD/PDF/DOCX → 「解析中」→「可检索」，分片数≥1
- [ ] 无效输入：`ftp://` 报「仅支持 http(s) 地址」；`http://192.168.1.1` 报「受限网络范围」；空正文时添加按钮禁用
- [ ] 判重：同 URL/同文件/同文本再导入 → 提示已存在 +「打开已有条目」（选中已有）/「仍然保留」（双份保留）
- [ ] 失败降级：登录墙/正文极短 URL → 「失败」态；检查器显示提取失败原因 +「重新导入」「手动粘贴正文」；手动粘贴预填原 URL 与标题
- [ ] 不轰炸：不可达域名失败后无自动重试刷屏，重启应用后失败态保持稳定
- [ ] 系统入口：WEB 条目「打开原网页」走系统浏览器；「在资源管理器中显示」定位数据目录 `files\<record_id>\*.md` 快照
- [ ] 可检索性：Ctrl+K 全局搜索能命中新入库条目标题
- [ ] 回归：收件箱粘贴/文档导入正常且新捕获出现在资料库；既有数据浏览/收藏不受影响
- [ ] （可选）SQLite 直查：`SELECT count(*) FROM document_segments WHERE library_item_id='<条目id>'` ≥1