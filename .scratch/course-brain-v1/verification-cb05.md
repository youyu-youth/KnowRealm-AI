# CB-05 真机验收清单（用户执行，agent 不代勾）

前端审核工作台在 CB-11 才交付，本票验证走「API 直调 + SQLite 直查」。
所有接口都挂 `X-KnowRealm-Token` 头；响应字段为 snake_case（`canonical_name` 等）。

## 第 0 步：启动并拿到令牌/端口

1. 仓库根 `pnpm run tauri dev`（壳自动拉起后端）。
2. 另开 PowerShell，找出 sidecar 进程命令行：

```powershell
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -like '*--token*' } |
  Select-Object -ExpandProperty CommandLine
```

3. 从输出抄下三个值，设置会话变量（重启应用后令牌会变，需重抄）：

```powershell
$base = "http://127.0.0.1:<端口>"
$h    = @{ "X-KnowRealm-Token" = "<令牌>" }
$course = "<课程id>"          # 从应用里建好一门课
```

4. SQL 直查用默认数据目录 `%USERPROFILE%\KnowRealm\knowrealm.db`（应用运行中可直接只读查询；若遇锁先复制一份再查）。

## 第 1 步：造出候选概念（二选一）

**A. 真实构建（推荐）**：课程里至少有一条带转写/文档的记录，设置页配好 LLM Provider + 同意外部处理，然后：

```powershell
Invoke-RestMethod -Headers $h -Method Post "$base/api/courses/$course/brain/builds"   # 202
Invoke-RestMethod -Headers $h "$base/api/courses/$course/brain"                        # 轮询到 status=REVIEW
$cands = Invoke-RestMethod -Headers $h "$base/api/courses/$course/brain/concepts?status=CANDIDATE"
$cands | Select-Object id, canonical_name, suggested_target_id
```

**B. 不想跑 LLM 时**，SQLite 直插一个候选（构建路径已被 CB-04 验过）：

```sql
INSERT INTO concepts (id, course_id, canonical_name, normalized_name, description,
  concept_type, importance, status, source, created_at, updated_at)
VALUES ('cand-1', '<课程id>', 'ｍｖｃｃ 并发控制', 'mvcc 并发控制', '测试候选',
  'TERM', 3, 'CANDIDATE', 'AI_EXTRACTED', datetime('now'), datetime('now'));
```

## 第 2 步：逐场景验证

记下某正式概念 id 为 `$confirmed`、某候选 id 为 `$cand`（`Invoke-RestMethod` 对非 2xx 会抛异常，用 `try/catch { $_.ErrorDetails.Message }` 看错误体里的 `code`）。

| # | 操作 | 预期 |
|---|------|------|
| 1 合并建议 | `GET /brain/concepts?status=CANDIDATE` | 与某正式概念归一化名相似的候选带 `suggested_target_id/name`；不相似的为 null |
| 2 confirm+重命名 | `POST /brain/apply-review`，body 见下① | 200；快照 `concept_count`+1、`candidate_count`-1、status=READY |
| 3 重命名撞名 | confirm 另一候选，`new_name` 填已有正式名（可用全角/大小写变体如 `ｍｖｃｃ`） | 409，code=`COURSE_BRAIN_CONCEPT_EXISTS`；快照 candidate_count 不变 |
| 4 merge | merge 候选到正式概念（候选与目标有同记录出现时最能验计数合并） | 200；SQL 断言见下② |
| 5 跨课程 404 | merge 时 `target_concept_id` 填**另一课程**的概念 id | 404，code=`COURSE_BRAIN_CONCEPT_NOT_FOUND` |
| 6 dismiss→重建 | dismiss 一个候选；再触发构建 | dismiss 后 candidate_count 减；重建后出现**同名的全新候选**（id 不同，可再审） |
| 7 archive | `POST /brain/concepts/{id}/archive`（对 CONFIRMED） | 200，status=ARCHIVED；对 CANDIDATE 调用则 409，code=`COURSE_BRAIN_CONCEPT_STATE_INVALID` |
| 8 待归档徽章 | 在应用里软删某正式概念唯一来源记录，再 `GET /brain/concepts?status=CONFIRMED` | 该概念 `stale_archivable=true`；有活记录/零出现的概念为 false |
| 9 非法决策 | confirm 已 CONFIRMED 的概念 → 409 STATE_INVALID；`decisions: []` → 422；同一概念出现两次 → 422 | 状态机不被破坏 |

① 请求体示例（字段 snake_case）：

```powershell
$body = @{ decisions = @(
  @{ decision_type = "confirm"; concept_id = "$cand"; new_name = "MVCC 并发控制" }
) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Headers $h -Method Post -ContentType "application/json" `
  -Body $body "$base/api/courses/$course/brain/apply-review"
```

② merge 后 SQL 断言（`$cand`=候选 id，`$target`=目标 id）：

```sql
SELECT status FROM concepts WHERE id = '<候选id>';                 -- ARCHIVED（退役）
SELECT concept_id, evidence_count FROM record_concepts
 WHERE record_id = '<共同记录id>';                                  -- 同记录两行并一行，计数相加
SELECT resource_id, count(*) FROM source_anchor_links
 WHERE resource_type = 'CONCEPT' GROUP BY resource_id;              -- 全部指向目标，候选为 0
SELECT count(*) FROM segment_search_index
 WHERE entity_type='CONCEPT' AND entity_id='<候选id>';              -- 0（FTS 已清）
```

## 附：口径说明（验收时别当 bug）

- confirm 后概念的 `source` 仍是 `AI_EXTRACTED`（source=来源溯源，确认态看 status）——定稿口径。
- merge 除计数相加外还会：relevance 取最大、first_start_ms 取最早、KP 桥空位回填。
- 候选指向的 concept_relations 不随 merge 迁移（关系审核属 CB-06，查询侧已按 CONFIRMED 过滤）。
- 建议目标被归档后，候选的 `suggested_target_id` 自动消失（读取期派生，无悬空）。
