# 02 — en.json 全量翻译与资源一致性防线

**What to build:** 英文界面用户看到完整、地道的英文界面文案——en.json 对齐 zh.json 全部约 1040 个叶子 key（19 个命名空间：应用、导航、捕获、录音、设置、向导、命令面板、资产库等），领域术语按定稿对照（Record / Knowledge Point / Quick Note / Review Material / Capture / Course / Inbox / Mock Test）；此后新增 key 漏翻时，资源一致性防线测试立即暴露。

**Blocked by:** 01（en.json 骨架与 zh.json 终态须先落位——本票翻译基于其结构，key 一致性验收依赖其终态；勿与 01 同时开工）

**Status:** done

- [x] en.json 全量真实英文翻译（替换 01 落位的 zh 结构占位副本），AI 翻译产出 + 人工抽查术语与高频界面
- [x] 术语对照遵守 CONTEXT.md 词条与 Avoid 撞词的英文处理（如「学习会话/学习记录」统一 Record，不得出现 Session 撞词）
- [x] 计数类 key 按英文复数规则提供后缀形式（如 `_other`），不破坏 i18next 解析
- [x] 新增资源一致性测试：zh / en 递归 key 集合 diff 为空（容忍英文复数后缀）
- [x] fallbackLng=zh 保持不变：en 缺 key 时回显中文，兜底语义不回退
- [x] 门禁全绿（tsc / lint / prettier 全绿；vitest 357/358，唯一失败为与本票无关的既有问题，见下方门禁备注）

## 实施记录（2026-09-08）

- en.json 1046 个叶子 key 全量翻译，其中 11 个计数 key 拆为 `_one`/`_other` 复数形式（时长 3、模拟测试 5、习题面板 3）；`charCount`、`hotWordsDescription` 为纯计数显示，保留基础 key（已验证 count 传入时 i18next 回退基础值）。
- 防线测试 `src/i18n/locales.test.ts`：key 集合双向 diff + en 复数后缀折算；另含一条复数解析行为断言（1 hour / 2 hours / 基础 key 回退）。
- `onboarding.test.tsx` 语言步用例原在 en 语言下断言中文文案（01 时期 en.json 为中文副本所以碰巧通过），本票起改为断言真实英文文案。
- 门禁备注：vitest 357/358，唯一失败 `SidebarUserArea.test.tsx > 有昵称与头像时同步展示`（两个 complementary 角色）为 HEAD 既有问题——已基线验证（还原 en.json 为 HEAD 版本后同样失败），与本票改动无关。

## 用户真机验收（agent 不代勾）

- [ ] 英文界面全量浏览抽查：除 AI 生成内容外无中文残留
