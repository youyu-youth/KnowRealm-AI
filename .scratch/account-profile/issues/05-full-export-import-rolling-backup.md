# 05 — 全量导出/导入与滚动备份

**What to build:** 全量导出：设置页触发 → `exports/knowrealm-export-YYYYMMDD-HHMMSS.zip`（manifest.json〔app_version/db user_version/created_at/include_secrets/文件清单〕+ VACUUM INTO db + files/** + config/**，默认排除 providers.json，勾选含时 UI 明示明文风险 #11；导出期间不停写）。导入：sidecar 启动参数 `--import-archive <zip>`，ensure_data_dir 后、目录锁与开库前校验落位（Python zipfile）——manifest/结构不符或 user_version>当前 → 拒绝且不留半成品；<当前 → 现有迁移自动升级；RUNNING/PENDING 任务原样入包、新机自动续。入口：首启向导（06 接线）+ 设置页空库限定兜底（无课程+无记录+无档案时可见）。滚动备份：启动 lifespan 当日快照 `VACUUM INTO backups/`、仅保留 7 份自动清理。

**Blocked by:** 03 — 数据目录分区、desktop.json 与打开目录

**Status:** done（真机项待用户验收）

- [x] 工单第一步验证：捕获临时文件确落 `cache/`（files/ 无竞态；结论落注记，若否则导出退化为停 worker）
- [x] `POST /api/settings/data-directory/export {include_secrets}`：同步端点+前端遮罩防重复；manifest+VACUUM INTO+zip 组装
- [x] `--import-archive` 启动参数：开库前校验落位；全部拒绝路径无残留
- [x] 空库判断只读端点 + 设置页兜底入口（非空隐藏）；导入触发=relaunch 带导入参数
- [x] 滚动备份：启动 lifespan 当日快照、保留 7 份清理
- [x] 后端测试（zip 结构/导入校验矩阵/user_version 双向/备份清理）+ 前端测试；pyright/tsc/prettier 全绿
- [ ] 真机人工验收（用户执行）：导出→新机（或新目录）导入数据完整、进行中任务续跑；含密钥勾选风险提示；导出包版本高于当前被明确拒绝

> **实现注记（2026-08-30）**：
> - **工单第一步结论**：音频导入（cache/imports）、录制暂存（cache/staging）、转写分片（cache/audio）本就落 `cache/`；但发现两处例外并已修正——文档导入临时文件原写 `files/{record_id}/.{file_id}.tmp`、头像覆盖写 `files/avatar.{ext}` 直写非原子。两处均改为 `cache/` 临时文件 + `os.replace` 原子落位，`files/` 从此只接收完整文件，导出遍历无部分写入竞态，**导出不停 worker**（且停 worker 也挡不住 API 路径的上传写，修根因是唯一正解）。
> - **导出**（`app/services/archive_service.py`）：`VACUUM INTO` 参数绑定路径、另开连接 WAL 安全快照；zip 组装全程 `asyncio.to_thread`；`config/*.tmp`（local_config 原子写中间文件，含明文密钥的 providers.tmp）永不入包；导出期间并发删除的文件跳过且 **manifest 文件清单同步剔除**（否则产出导入端必拒的「清单与包内容不一致」自拒包，两处均有回归测试）。manifest 五字段齐备，app_version 统一来自新 `app/core/version.py`。
> - **导入**：lifespan 中 ensure_data_dir → `restore_archive`（校验+落位）→ 目录锁 → run_migrations（<当前自动升级；`supported_user_version()` 自 migrations.py 抽出共享）。校验矩阵错误码 `IMPORT_ARCHIVE_{MISSING,INVALID,VERSION_TOO_NEW,TARGET_NOT_EMPTY}`：非 zip/缺 manifest/清单与包不符/非法路径/版本过新/目标非空库（无课程+无记录+无档案，软删数据视为非空）全部在**解压前**拒绝故无残留；落位走 `cache/import-archive` 暂存，files/config 先合并覆盖、db 最后原子替换，失败清暂存。空库端点 `GET /api/settings/data-directory/library-state`。
> - **触发链（壳）**：`import_from_archive` command = 校验文件存在 → 写 `app_config_dir/pending-import.json`（一次性，启动即消费删除；ADR-0013 之外的瞬态文件）→ 停 sidecar 释放目录锁；前端复用迁移的 restartPending + 生产 relaunch / dev manualRestart 语义（relaunch 在 dev 会白屏，04 已证）。06 向导可直接复用同一 command。版本过新的拒绝发生在 relaunch 后的 sidecar 启动期：进程非零退出、错误码进 backend.log，真机验收时以此与「应用启动失败」区分。
> - **滚动备份**：lifespan run_migrations 后执行（备份迁移后的库），当日快照不存在才创建，保留最近 7 份；失败仅记 `ROLLING_BACKUP_FAILED` 日志不阻断启动（对齐 tombstone 清理的容错模式）。
> - **规则同步**：`.claude/rules/fastapi.md` §7 启动定序补导入「锁前落位」例外（工单规格优先于原规则表述）。
> - **门禁实测（2026-08-30）**：后端全量 319 过（含 test_archive.py 15 例：zip 结构/排除项/校验矩阵/版本双向/备份清理/清单一致性/tmp 排除 + test_server_process.py 新增 2 例真实进程 `--import-archive` 全链路）；cargo test 21 过、clippy -D warnings 零告警；前端 DataDirectorySection 17 例过（新增 8 例：导出默认/含密钥风险/遮罩防重复/失败可关、导入入口空库限定/确认重启/失败不重启可重试/dev manualRestart）、tsc 双配置零错、prettier（改动文件）/eslint 净；pyright 仅剩既有 `logging.py` 报错（与本工单无关）；api-types 已随 schema 重新生成并过 check。TodoPanel 全量跑的 1 例失败为既有抖动（单跑通过，同 04 记录）。
