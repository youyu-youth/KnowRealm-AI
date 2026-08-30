# 02 — 供应商分区：AI 服务卡、ASR 卡与就地收敛

**What to build:** 设置页新增"供应商"分区：**AI 服务卡**（base_url+api_key+model 单 active；DashScope 预设按钮一键填充 compatible-mode base_url + `qwen-plus`；连接测试复用现有 `POST /tests`）与**语音转写卡**（腾讯 ASR key：GET/PUT 对齐 llm 模式、空 key 保留旧值；连接测试=TC3 调只读轻接口，选不出合适接口退化为格式校验）。聊天空态与总结面板的旧就地表单删除、改为"未配置 → 提示 + 跳设置页"（可留只读状态展示）。Embedding 无配置 UI（卡内文案注明 V1 固定）。配置≠同意原则在文案明示。（决策细节见 plan 14）

**Blocked by:** None — can start immediately

**Status:** done（真机项待用户验收）

- [x] 工单第一步调研：腾讯 ASR 是否存在无需业务资源的只读轻接口可验证凭据+region（结论落工单注记；选不出则测试退化为格式校验，不硬做）
- [x] `GET/PUT /api/settings/providers/tencent-asr`（secret_id/secret_key/region；空 key 保留旧值）；若调研出接口则加 `POST …/tests`；api-types 重生成
- [x] 设置页供应商分区骨架 + AI 服务卡（DashScope 预设填充、连接测试、保存状态展示）
- [x] 语音转写卡（key 配置、测试/校验反馈、"配置 key 不等于同意外发"文案）
- [x] 就地收敛：`ChatProviderSetup` 与 `SummaryPanel` 的 ProviderConfiguration 表单删除改跳设置页引导
- [x] 后端+前端测试；pyright/tsc/prettier 全绿
- [x] 真机人工验收（用户执行）：自定义端点配置→连接测试通过→总结/chat 走该端点；DashScope 预设填充；ASR key 配置后转写可用

> **实现注记（2026-08-30）**：
> - 连接测试 = `TencentAsrClient.test_credentials` 真实 TC3 调 `GetAsrVocabList`（`Limit=1`），AuthFailure / 未开通 / 欠费停服分别映射中文反馈（`_asr_test_error_detail`）。
> - `clear_secret_key` 对齐 llm 的 `clear_api_key` 模式，且语义为**清除整对凭据**（SecretId/SecretKey 一起清，region 保留）；半凭据无消费价值。
> - `load_tencent_asr_provider`（按 providers.json 事实读，允许空密钥，设置页用）与 `load_tencent_asr_config`（全字段非空才可用，ASR worker 用）拆分；providers.json `llm`/`tencent_asr` 单键结构未动。
> - `app.state.asr_client` 抽出供测试端点复用（原 audio_factory 闭包内构造）；测试注入走 `TencentAsrClient(transport=…)` 真签名链路。
> - 就地收敛删除 `ChatProviderSetup.tsx`，新增共享 `components/common/ProviderSetupGuide.tsx`（chat 空态 + SummaryPanel 三处 CONFIGURE_PROVIDER/未配置态统一跳设置页；SummaryProviderSettings 保留只读状态行，"更改"改跳设置）。
> - 与工单 01 并行开发：01 先行提交时带走了共享文件（keys.ts / SettingsPage.tsx / zh.json / handlers.ts / settings.test.tsx / api-types）中属于本工单的 hunk（tencentAsrProvider key、ProvidersSection 挂载、providerGuide+settings.providers 文案、asr 默认 mock、供应商分区测试、TencentAsr* schema），本工单提交含其余全部文件。

> **调研结论（2026-08-30）**：选用 `GetAsrVocabList`（语音识别列举热词表，[文档](https://cloud.tencent.com/document/product/1093/41484)）。
> 只读列举类接口，不创建/修改任何资源；业务参数全可选（`Limit=1` 即可），无热词表时返回空列表同样成功；
> 与正式转写同走 `asr.tencentcloudapi.com` + TC3 签名 + `X-TC-Region` 头，凭据错误会得到 `AuthFailure.SignatureFailure / SecretIdNotFound / InvalidSecretId` 等可区分错误码；
> 服务未开通/欠费为 `FailedOperation.UserNotRegistered / ServiceIsolate`，同样给出明确反馈。
> Region 在该接口文档中为可选公共参数，测试真实携带所配 region 发送——region 被拒即报错、被接受即通过，凭据为主验证目标。
> 故连接测试为真实 TC3 轻调用（`POST /api/settings/providers/tencent-asr/tests`），无需退化为格式校验。
