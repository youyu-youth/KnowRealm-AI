# 01 — 档案补全：昵称、头像与消费联动

**What to build:** 设置页档案表单支持昵称与头像：选图（png/jpg/webp，≤2MB）经 sidecar 存储（覆盖式 `files/avatar.<ext>`）、可删除；侧边栏底部用户区展示头像+昵称（空昵称占位，点击跳设置页档案区，不激活"学习画像"禁用导航项）；建课程对话框按角色预选默认场景（STUDENT→SCHOOL、DEVELOPER/OFFICE_WORKER→CAREER，可改；无档案/OTHER 不预选）。昵称不进任何 AI prompt（`build_profile_snapshot` 不动）。（决策细节见 `.scratch/function-plans-introduction/14-account-profile.md`）

**Blocked by:** None — can start immediately

**Status:** done（真机项待用户验收）

- [x] ProfileOut/ProfileUpdate 增 nickname（≤20 字，清洗规则对齐 about_me）；api-types 重生成
- [x] `PUT/GET/DELETE /api/profile/avatar`：原始字节体、魔数+≤2MB 校验、覆盖式写 `files/avatar.<ext>`、`avatar_file` 存相对路径；UI 不直读数据目录（前端 fetch 转 blob URL 展示）
- [x] 设置页表单：昵称输入+头像选择/预览/删除；保存后以服务端事实重挂载回显（沿用现有 key 模式）
- [x] 侧边栏底部用户区：头像+昵称（空昵称占位）、点击跳设置页档案区
- [x] 建课程表单按 `primary_role` 预选 `learning_context` 初值；无档案/OTHER 不预选；后端契约不动（必填无默认）
- [x] 后端测试（昵称长度/头像格式与大小校验/删除清理文件）+ 前端测试（表单/用户区/预选）；pyright/tsc/prettier 全绿
- [x] 真机人工验收（用户执行）：真实选图上传显示、重启保持、侧边栏展示、建课预选

## 实现注记（2026-08-30）

- 头像选图最终用 HTML `<input type="file">`（WebView2 原生选择器）：计划选型表的 tauri-plugin-dialog `open` 需要配套 `fs:allow-read-file` 全盘 scope 才能读用户所选路径，与 docs/rules/desktop-tauri.md §3 权限最小化冲突（评审定稿改道）；零新增权限，dialog:allow-open 留给工单 03 的目录选择。
- 后端文件 IO 全部经 `asyncio.to_thread`（fastapi.md §4）；换格式覆盖上传会清理其它扩展名的旧头像文件。
- 建课预选用"渲染期派生"实现：用户未选场景且对话框打开时场景值随档案派生（STUDENT→SCHOOL、职场角色→CAREER），用户选定后以用户为准，档案晚到不覆盖也不抹掉已输入字段（react-hooks set-state-in-effect 规则要求）。
- 昵称不进任何 AI prompt：`build_profile_snapshot` 未动（chat_session_service.py 零改动）。
