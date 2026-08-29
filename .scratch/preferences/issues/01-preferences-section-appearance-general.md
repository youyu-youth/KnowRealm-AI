# 01 — 偏好分区与外观/通用偏好（读写基座）

**What to build:** 设置页新增「偏好」分区并一次成型两组控件——外观（深色模式 LIGHT/DARK/SYSTEM、字号 S/M/L）与通用（时区、默认习题数量）——全部即改即存、失败行内报错、重启保持；偏好读写契约定型为全字段 optional 部分更新（缺键=默认、未知键保留），后续桌面行为票只往里加键。「桌面行为」小节随 02 进入，本票不留空壳占位。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `PUT /api/settings/preferences` 改全字段 optional 部分更新（merge 语义、响应恒全量）；`theme`（LIGHT/DARK/SYSTEM）、`font_scale`（S/M/L）、`timezone`（null 或 IANA 白名单值）校验，非法 422；缺键=默认不回写；consent 等未知键保留
- [ ] OpenAPI → api-types 重新生成；`quiz_last_count` 既有调用方（习题生成对话框）传法不变、行为兼容
- [ ] 深色模式三态：DARK 挂 `.dark`、LIGHT 挂 `.light`、SYSTEM 双摘由 `prefers-color-scheme` 自动跟随；切换全应用即时生效；首帧按 SYSTEM 渲染、偏好到达后应用（接受一次骨架变色）
- [ ] 字号 S/M/L = 根字号 15/16/18px 等比缩放（token 全 rem），布局不破；M 为缺省不写键
- [ ] 控件级即改即存（无保存按钮），保存失败行内报错并回显服务端事实——该模式为全偏好分区定型复用
- [ ] 时区：搜索式下拉（原生 `Intl.supportedValuesOf('timeZone')` 数据源），默认项「跟随系统」存 null
- [ ] `quiz_last_count` 迁入通用小节，与习题生成对话框双入口同键、统一失效同一 query key
- [ ] 后端 HTTP 测试（部分更新合并 / 缺键默认 / 未知键保留 / 校验矩阵 / 写后读回）与前端 MSW 测试（分区渲染 / 即改即存负载 / 失败回显 / 主题 class 与根字号应用 / 双入口同步）通过
