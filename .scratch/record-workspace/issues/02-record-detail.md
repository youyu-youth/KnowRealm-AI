# 02 — 可直达的 Record 详情

**What to build:** 用户可以从课程列表进入 Record 工作区，也可以直接打开或刷新某个 Record 的全局地址；页面始终展示真实 Record 元数据，默认进入可用但诚实为空的 Summary，其余尚未实现的资产页签明确禁用。

**Blocked by:** 01 — 课程中可查看真实 Records

**Status:** completed

- [x] `GET /api/records/{record_id}` 受启动令牌保护，返回与列表相同的统一 Record 输出合同，且不暴露 `deleted_at`。
- [x] Record 不存在、Record 已软删除或其非空父课程已软删除时返回 404；`course_id=NULL` 的未删除 Record 可以正常读取。
- [x] 全局 Record 地址支持列表导航、直接打开和刷新恢复，不依赖先进入课程页或进程内临时状态。
- [x] 页面具有加载、失败重试和不存在状态；返回动作对课程 Record 回到对应课程的 Records 页签，对无课程 Record 回到 Spaces。
- [x] 页头显示标题、采集类型、状态、创建时间和时长，并与列表使用同一标题回退与状态文案规则。
- [x] Summary 是默认且可用的页签；尚无总结时显示真实空态，不放示例总结、不触发总结生成，也不把空态伪装成处理中。
- [x] Transcript、Highlights、Notes、Flashcards 和 Quiz 保持可见但禁用，并通过禁用语义和辅助说明让键盘及读屏用户知道当前不可用。
- [x] 页签可用性是本切片固定的产品配置，不新增 `available_assets`、资产探测接口或为未来页签预建状态管理。
- [x] `FAILED` 只显示通用失败说明；不展示失败来源、恢复动作或重试按钮，也不新增 `processing_jobs`、轮询或 SSE。
- [x] API 测试覆盖正常详情、空课程归属、Record tombstone、父课程 tombstone、404 与鉴权；前端测试覆盖直接路由、刷新数据恢复、返回路径、各页面状态和页签可访问性。
- [x] 使用真实 sidecar、随机 localhost 端口和启动令牌验证详情请求；桌面 Network 证据必须表明页面读取的是详情接口而不是 mock 或列表缓存伪装。
- [x] 在 1440×900、1280×800、1099×720 以及明暗主题下检查页头、空态、禁用页签、焦点与无水平溢出；结果按静态、测试、HTTP、Network、渲染证据分层记录。
