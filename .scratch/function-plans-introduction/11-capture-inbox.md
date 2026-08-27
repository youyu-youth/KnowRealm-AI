# 11 - 轻捕获与收件箱

> Wave: A（Wave B 增段：整理增强）｜ PRD: §4.3.0 / §6.6 ｜ 决策引用: #29 #30 #51

## 功能描述 / 目标

五级捕获的轻端（L1 速记 / L2 粘贴）与收件箱（Inbox）最小闭环，并承接 05 未实现的未选课文档入口：先捕获后整理——未归类内容不耗 token，归类 / 升级 / 删除三动作事后处理。

## 功能范围

**做（Wave A）**：
- ⚡速记：全局快捷键（固定 Ctrl+Alt+N，#51）弹出输入框，一句话~几段，存 Inbox（NOTE 态）；本 plan 同步交付最小关窗驻留、托盘“显示 / 退出”与固定快捷键，13 只接管自定义快捷键、开机自启及其他偏好
- 📋粘贴长文本：与速记复用同一文本捕获组件，但保留独立“粘贴文本”入口与 PASTE 类型；课程可选，**未选课 = 仅存储 NOTE；已选课 = 直接进总结管线**（#29），不得按字数或浏览器 paste 事件猜测类型
- Inbox 视图：course_id 为空的学习记录时间流（左栏入口）
- 三动作：**归类**（填 course_id，不触发 AI）/ **升级**（一次用户操作内选择 ACTIVE 课程、完成归类并触发 06 总结管线）/ **删除**
- 未选课录音（03/04 停于 SUMMARY_PENDING 的记录）在此归类 + 升级进同一闭环（#30）
- 当前统一 Capture Batch 中的纯文档、多文档、纯音频、音频+文档批次都允许选择或不选择课程；文档复用 05 的解析能力并立即本地解析。未选课批次进入 Inbox，按 CONTENT_PROCESSING → SUMMARY_PENDING 或 FAILED 保留真实业务态，可重新发现、重试或删除；归类前不创建 Summary Job，不得把文档静默等同 NOTE
- 速记 / 粘贴入口挂载 01 已提供的顶部快速捕获栏；Record 实体、列表与详情复用 02

**做（Wave B 增段）**：
- Inbox 整理增强：批量归类 / 按类型筛选

**不做**：
- 网页剪藏 L3（P2）、速记直接生成知识点、自动归类建议

## 核心业务流程

快捷键 → 速记框 → 存 Inbox（NOTE）→ 事后整理：归类（纯归档）/ 升级（选择 ACTIVE 课程并在同一操作中触发总结 HITL）/ 删除；已选课粘贴跳过 Inbox 直接进管线。文档无论是否选课都先完成本地解析，课程只控制归属与 AI 总结资格。

## 关键业务规则

- **未归类内容不触发 LLM / Summary 调用**（#29）：NOTE 态纯存储；未选课录音仍按 04 在外部处理同意与 ASR 凭据满足后完成转写，相关 ASR 调用不属于总结 token
- **升级必须先归类 ACTIVE 课程**（#29）：learning_context / education_stage / depth 是总结 AI 上下文硬依赖，无课程或归档课程不总结
- 归类不触发管线，升级才触发（#29）
- 速记纯存储，无任何 AI 调用
- Inbox 是 `course_id IS NULL` 的 Record 集合，不是新增业务态；NOTE 只用于无需内容处理的速记 / 未选课粘贴，录音与文档保留各自真实处理状态
- Provider 未配置或未取得外部处理同意时，本地捕获、文档解析与归类仍须成功；升级后的 Record 停在 SUMMARY_PENDING，待条件满足后继续
- 速记 / 粘贴在同一事务创建 Record 与 Transcript；已选课粘贴直接为 SUMMARY_PENDING，未选课文本为 NOTE。编辑 NOTE 只更新 Transcript 并保持 NOTE，升级时才推进到 SUMMARY_PENDING；编辑正文不自动重算标题
- 只有 NOTE / SUMMARY_PENDING 可归类或升级；CONTENT_PROCESSING / FAILED 只显示进度、重试或删除，避免纯归类后被既有内容完成器误触发 AI
- 文本标题取正文第一条非空行的前 100 个 Unicode 字符，不单独要求标题；正文拒绝空白，UTF-8 超过 1 MiB 时提示改用 TXT / MD 文档导入
- 固定快捷键注册失败不阻止应用启动，应用内入口仍可用并显示一次明确提示；触发成功时统一显示并聚焦主窗口、打开唯一速记框，不叠加弹窗。关闭窗口只隐藏，托盘“退出”才结束 sidecar 与应用
- 使用明确业务命令：新增 `POST /api/text-captures`、`GET /api/inbox`、`POST /api/records/{id}/classification`、`POST /api/records/{id}/upgrade`；复用既有 Record 详情、删除与 Job 重试，不开放通用 Record 创建 / PATCH / 搜索接口。文档导入只把既有 course_id 改为可空
- 纯归类成功后留在 Inbox 并移除该行，显示归属结果；升级成功后进入该 Record 的 Summary 页。同课程重复命令按成功处理，已归到其他课程返回 409，本 plan 不支持重新归类
- Inbox 打开 Record 默认进入 Transcript；无课程详情返回 Inbox，Summary 使用准确的 COURSE_REQUIRED 提示“请先归类并升级”，不得复用“课程已归档”；有课程详情仍返回对应课程 Records
- 托盘退出仅在没有活动录音和未保存文本时直接执行；否则显示并聚焦主窗口，明确提示最新未落盘录音片段或未保存正文可能丢失，用户确认后才停止 sidecar 并退出
- 速记固定不选课程；粘贴与文档的课程选择器始终默认“暂不归类”，即使从课程页面打开也不自动预选。只有用户明确选择 ACTIVE 课程才具备自动总结资格
- 纯归类后的 Record 只在详情 Summary 页提供后续升级：已归类 NOTE 先推进到 SUMMARY_PENDING，已归类 SUMMARY_PENDING 直接尝试入队；无课程详情的升级入口自带 ACTIVE 课程选择器，已有活动 Summary Job 时复用而不重复创建
- 本地数据提交与 AI 入队分离：先提交 Record / Transcript / course_id / status，再尝试创建 Summary Job。Provider 缺失、未同意、离线或临时入队失败都不回滚本地内容；返回本地成功、记录失败并在 Summary 页保留继续入口
- Wave A 的 Inbox 只按 created_at 倒序读取全部未软删、course_id 为空的 Record；不做分页、虚拟滚动、筛选或批量操作，后两项留在 Wave B，真实数据量造成性能问题时再引入游标分页
- 速记 / 粘贴没有原始文件，只创建 Record + Transcript，不伪造 record_files；Transcript 初始为 language=und、source_version=1、edited_by_user=false，用户后续编辑才置 true
- 当前桌面导入入口以 Capture Batch 为事实路径：移除“含文档必须选课”的旧限制；旧 `/api/document-imports` 同步把 course_id 改为可空，避免两个公开入口语义冲突。所有组合无课程时照常完成 Transcript 并停在 Inbox
- 文本捕获返回 record_id + 可空 summary_job_id；归类返回最新 RecordOut；升级返回最新 RecordOut + 可空 summary_job_id。summary_job_id 为空表示本地操作已成功但 AI 尚未启动，前端随后重读 Record / Summary，不从命令响应伪造处理结果

## 前置依赖

- 01（Inbox 视图挂载既有左栏与路由出口）
- 02（记录实体、列表与详情复用）
- 05（复用单文件文档解析、processing_jobs、失败与删除语义）
- 06（升级触发的总结管线）
- Tauri 最小全局快捷键、关窗驻留与托盘生命周期由本 plan 随首个消费者交付；13 仅在其上增加可配置偏好

## 验收标准（出口线）

- [ ] 任意界面快捷键唤起速记 → 保存 → Inbox 时间流出现（NOTE 态）
- [ ] 未选课粘贴 → NOTE 纯存储，无 AI 调用发生；已选课粘贴 → 直接进总结
- [ ] 速记与粘贴使用明确入口并写入正确 capture_type；空白或超过 1 MiB 的正文不创建 Record，快捷键冲突不阻止应用内捕获
- [ ] Inbox 中先归类再升级 → 进入总结 HITL 闭环走通
- [ ] 纯归类后留在 Inbox 继续整理，升级后进入 Summary；重复同课程命令幂等，跨课程重复返回 409
- [ ] 无课程 Record 从 Inbox 进入 Transcript 并可返回 Inbox；Summary 显示 COURSE_REQUIRED 而非“课程已归档”
- [ ] 已归类 NOTE 可从详情升级，重复升级不创建第二个活动 Summary Job；Provider / 同意 / 入队故障不回滚已保存正文或归类结果
- [ ] 速记 / 粘贴只创建 Record + Transcript 且元数据正确，不产生 record_files；Inbox Wave A 按时间倒序展示全部未归类 Record
- [ ] 未选课录音转写完成后，归类 + 升级解锁总结（#30 闭环）
- [ ] 文档导入选择 ACTIVE 课程或不选择课程均可受理并立即本地解析；未选课文档可从 Inbox 重新找到、重试和删除，归类到 ACTIVE 课程后升级进入 06，且全过程不在未归类时调用 AI
- [ ] 关闭窗口后托盘与快捷键仍可重新显示应用；存在活动录音或未保存文本时托盘退出必须确认，无待保存内容时可完整停止 sidecar 并退出
- [ ] （Wave B）批量归类多条生效

## 后续交付方式

- 本轮只维护功能计划与术语共识；spec 由后续 `to-spec` 生成，issues 由后续 `to-tickets` 生成，本轮不提前创建对应文件
- `to-tickets` 按 `01 → 02 → 03` 生成三张纵向票：文本/可选课程导入到 Inbox；归类/升级到既有 Summary/HITL；全局快捷键/托盘/安全退出与 Wave A 总验收
- 验收证据分层记录：SQLite/API 与自动化检查；真实 localhost HTTP 与重启持久化；真实 Windows/Tauri 快捷键、托盘和退出；可观测 fake Provider 的未归类零 Summary 调用与升级单次调用。11 不把既有或模拟 ASR 冒充新的真实腾讯请求
- Wave B 批量归类/筛选、分页、重新归类、快捷键自定义、开机自启、自动归类建议、网页剪藏及新的 AI/ASR Provider 能力继续排除
