# 01 — 偏好分区与外观/通用偏好（读写基座）

**What to build:** 设置页新增「偏好」分区并一次成型两组控件——外观（深色模式 LIGHT/DARK/SYSTEM、字号 S/M/L）与通用（时区、默认习题数量）——全部即改即存、失败行内报错、重启保持；偏好读写契约定型为全字段 optional 部分更新（缺键=默认、未知键保留），后续桌面行为票只往里加键。「桌面行为」小节随 02 进入，本票不留空壳占位。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `PUT /api/settings/preferences` 改全字段 optional 部分更新（merge 语义、响应恒全量）；`theme`（LIGHT/DARK/SYSTEM）、`font_scale`（S/M/L）、`timezone`（null 或 IANA 白名单值）校验，非法 422；缺键=默认不回写；consent 等未知键保留
- [x] OpenAPI → api-types 重新生成；`quiz_last_count` 既有调用方（习题生成对话框）传法不变、行为兼容
- [x] 深色模式三态：DARK 挂 `.dark`、LIGHT 挂 `.light`、SYSTEM 双摘由 `prefers-color-scheme` 自动跟随；切换全应用即时生效；首帧按 SYSTEM 渲染、偏好到达后应用（接受一次骨架变色）
- [x] 字号 S/M/L = 根字号 15/16/18px 等比缩放（token 全 rem），布局不破；M 为缺省不写键
- [x] 控件级即改即存（无保存按钮），保存失败行内报错并回显服务端事实——该模式为全偏好分区定型复用
- [x] 时区：搜索式下拉（原生 `Intl.supportedValuesOf('timeZone')` 数据源），默认项「跟随系统」存 null
- [x] `quiz_last_count` 迁入通用小节，与习题生成对话框双入口同键、统一失效同一 query key
- [x] 后端 HTTP 测试（部分更新合并 / 缺键默认 / 未知键保留 / 校验矩阵 / 写后读回）与前端 MSW 测试（分区渲染 / 即改即存负载 / 失败回显 / 主题 class 与根字号应用 / 双入口同步）通过

## 实现注记（2026-08-29）

- 「写默认值=删键」按 spec「M 不写键」泛化为统一规则（`PREFERENCE_DEFAULTS`）：settings.json 只保留偏离项，读回等价、quiz_last_count=5 不再落盘但 GET 结果不变，由 `test_put_default_values_remove_preference_keys` 固化。
- SYSTEM 三态落地为**应用器解析**而非字面双摘：`applyTheme` 读 `prefers-color-scheme` 后同样挂 `.dark`/`.light`，并监听系统切换。原因：`@custom-variant dark` 是 class 策略（实测嵌套 @media 的混合块会被 Tailwind 4.3 静默丢弃、整变体失效），真双摘会让系统深色下全部 `dark:` 工具类失效；首帧仍由 `theme.css` 媒体查询兜底。`desktop-ui.md` §5 已同步修订表述。
- timezone 后端校验用 `zoneinfo.ZoneInfo`（新增 backend 依赖 `tzdata`——Windows 无系统 tz 库）；读侧对脏存量值同样回退默认。
- 双入口同步测试落点：写侧 `{quiz_last_count}` 单字段负载（settings.test 即改即存 + QuizPanel.test 生成后写回）、读侧 GET 预选（QuizPanel.test），两端共用同一 URL 与 query key。
- 时区搜索下拉为受控自写控件（无 cmdk/Popover 依赖，spec 限定唯一新前端依赖为 react-hotkeys-hook）；键盘仅 Escape/外点关闭，未做方向键导航——与 desktop-ui.md §6 存在已知张力，02 票如需可升级。
- 测试环境：jsdom 无 `matchMedia`，`src/test/setup.ts` 补 stub；TodoPanel「生成候选后可修剪并整批采纳」在全量并发下间歇超时为**既有抖动**（基线无本改动同败），与本票无关。
