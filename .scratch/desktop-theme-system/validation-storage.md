# 独立主题系统：存储与契约阶段验收

日期：2026-10-10。实施提交：9833a23。审查基线：ee06877c8210388829d399dad5f24ce212cf544b。

## 当前实现范围

- 两组独立 Literal 主题 ID，由后端请求契约校验模式归属，读取目录从相同 Literal 推导。
- 复用偏好 API、部分更新、缺键默认、默认删键、未知键保留和原子文件替换；不增加数据库迁移。
- settings.json 的偏好、ASR 同意、LLM 同意、记忆外发开关、Agent 默认授权档五个写入口共享提交锁，锁保护完整读改写及返回值读取。
- 扩展 OpenAPI 与生成 TS 类型，更新现有类型化夹具及 MSW 默认偏好。
- 全量归档真实导出、导入后，通过偏好 API 重新读回模式和两组主题；未改滚动数据库备份范围。

## 已运行的检查

| 检查 | 结果 |
| --- | --- |
| backend：`uv run pytest tests/test_preferences.py tests/test_archive.py --basetemp=.pytest-theme-final -q` | 78 passed，104.65s |
| backend：全量 `uv run pyright` | 0 errors / warnings |
| backend：触及的两个生产文件及两个测试文件 Ruff lint / format check | 通过 |
| desktop：`pnpm build` | TS 检查及构建通过；既有大 chunk 提示保留 |
| api-types：`pnpm --filter @knowrealm/api-types check` | OpenAPI 与生成类型漂移检查通过 |
| desktop：触及的三个 TS 文件 ESLint / Prettier | 通过 |
| desktop：`pnpm test -- --maxWorkers=4` | 75 文件：69 通过、6 失败；695 用例：686 通过、9 失败；319.46s。i18n 一致性 3 项通过 |
| desktop：`pnpm lint` | 失败：未修改的 PlanDraftEditor.tsx:55、LearningPlanTab.tsx:760 各一条 react-refresh/only-export-components 警告，max-warnings=0 拦截 |
| `git diff --check` | 通过 |

全量前端失败文件（来自本轮 Vitest 结果缓存）：RecordDetail.test.tsx、inbox.test.tsx、TodoPanel.test.tsx、CommandPalette.test.tsx、CourseBrainReview.test.tsx、LearningPlanTab.test.tsx。它们及相关生产组件未被本次修改；尚未在旧 HEAD 做对照复跑，不把全部失败归因为资源抖动，也不宣称全量门禁通过。当前前端只改变偏好夹具和 mock 的两个字段，没有修改外观或业务执行逻辑。

## code-review 双轴审查

Standards：未发现实质规范违规或需要整改的代码气味；独立 Literal、读取回退、请求校验、共享锁及 to_thread 调用边界清晰，复用既有文件存储，没有新增通用配置框架。

Spec：本阶段未发现可确认逻辑缺陷、范围扩大或状态失真。两组归属、缺键默认、部分更新、竞争修复、契约生成与归档读回符合本阶段范围。

两个独立子代理只做静态审查，未重新运行测试或真机验收。审查通过仅指本阶段，不代表整票完成。

## 待批准与剩余范围

具体权威文档提案见 [authority-proposal.md](authority-proposal.md)。工单明确要求：“进入新增配色实现前提交设计规范与领域术语的具体修改提案，批准后再写权威文档”；截至本阶段收口尚未获得该项批准。

DESIGN.md / GLOSSARY.md 保持原样。主题登记与新增配色、两组 UI、立即生效、保存失败对账与重试、前端冲突控制、目录隔离缓存、启动核对、系统事件恢复、计算样式消费方刷新均未实施。T16 仅证明归档字段恢复，目录迁移及缓存校正尚未验收。所有真实 Tauri / WebView2 / Windows 缩放、启动帧、业务不中断及视觉验收仍待完成；工单保持未完成。

未运行全量后端测试，未扩展无关历史测试覆盖。测试全部使用仓库临时数据目录，没有修改真实用户数据。

测试临时目录 `.pytest-theme-system`、`.pytest-theme-archive`、`.pytest-theme-final` 位于 backend 下；清理命令虽检查路径属于工作区，仍被自动审批以“blocked by policy”拒绝，目录保留且未纳入提交。原有未跟踪 spec.md 保持原状，未代为提交。
