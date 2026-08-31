# 01 — 题库扩五型题型（多选 / 填空）

**What to build:** 习题生成从三型扩为五型（单选/多选/判断/填空/简答）：生成对话框五型可选，AI 批次生成与构成校验支持新形态；记录详情的**逐题作答模式同步可作答新题型**——多选题勾选组合提交、填空题题干内嵌空位逐空填写。判分采全对制：全对=CORRECT、否则=WRONG（`answer_result` 两值语义不变，填空解析展示逐空情况）。本票是模拟测试（15）的题库前置。

**Blocked by:** 无 — 可立即开工。

**Status:** completed

**深度参考:** `.scratch/function-plans-introduction/15-mock-test.md`（题型五型定稿段）

- [x] 生成对话框题型勾选扩为五项；生成批次可含多选/填空，批次构成校验（题数/题型）通过
- [x] 多选题逐题作答：勾选提交，全对=CORRECT、否则=WRONG（缺选/错选均 WRONG）
- [x] 填空题逐题作答：题干内嵌空位（下划线式输入）逐空填写，全对=CORRECT、否则=WRONG，解析展示逐空对错
- [x] 迁移扩展 `question_type` CHECK（含 0010 job_type 相关断言核对），顶 6 处 user_version 断言同步
- [x] 后端 schema 变更后重跑 api-types 生成
- [x] pytest（生成/作答判分/一题一答幂等不回归）与前端 MSW（新题型控件/锁定态）双侧绿
