# 01 — 手动 Todo 闭环与页签挂载

**What to build:** 不经 AI 的完整小闭环：学习记录详情的「Todo」页签从禁用占位转为真实功能（解锁 = record COMPLETED），用户手工新增、编辑、删除待办条目并勾选完成（原位划线弱化、可取消恢复），勾选状态持久、重启后保持；总结尚未确认也不妨碍随手记账——手动操作不受任何门控限制。建表与级联同票完成，不留孤儿行。（裁决与契约细节见 `.scratch/todo/spec.md`）

**Blocked by:** None — can start immediately

**Status:** done

- [x] 迁移新建 `todo_items` 表（数据模型 v2.2 全列）：batch_id（可空）、content、status（TODO / DONE）、source（AI / MANUAL）、generated_from_summary_id（可空）、generation_status（可空 DRAFT / ACTIVE / SUPERSEDED）、sort_order、软删列；Record 软删同事务级联 todo
- [x] 手动 CRUD 端点：新增（source=MANUAL、sort_order 取最大值 +1 追加尾部）、编辑 content、删除（软删）、勾选切换（TODO↔DONE 幂等，重复置同态返回现状）
- [x] 读端点骨架一次立好（后续票只加分支不重构）：可见条目按 sort_order 混排 + active_job_id + blocked_reason 判定（SUMMARY_NOT_CONFIRMED / SUMMARY_SUPERSEDED / COURSE_ARCHIVED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED）；本票 action_required 恒 NONE
- [x] 手动增删改勾在任何 blocked_reason 与无总结状态下全部可用（仅生成入口受限，生成属后续票）
- [x] 「Todo」页签转正：解锁 = record COMPLETED，未完成保持禁用占位；blocked 空态给下一步指引（未确认总结指向总结页签、未同意时一键授权）
- [x] 清单 UI：勾选 checkbox 划线弱化原位保留、行内编辑、删除、新增表单；文案全走 i18n，纯图标按钮带 aria-label
- [x] 后端 ASGI + 真实迁移库 HTTP 全流程测试（CRUD、勾选持久与幂等、追加排序、级联软删、blocked 下手动可用）；前端 MSW + `?tab=todo` 渲染断言（页签解锁、勾选编辑增删、划线样式）
