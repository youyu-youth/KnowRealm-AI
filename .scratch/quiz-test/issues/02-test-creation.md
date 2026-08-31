# 02 — 测试数据层与组卷闭环

**What to build:** 从课程页发起模拟测试并看到一张卷：课程详情页第三个 tab「模拟测试」承载历史测试列表（进行中/已完成/已放弃）与组卷对话框（五型题型多选 + 题量 5/10/20）；组卷 API 在课程题库随机抽 ACTIVE 习题建卷（存量不足抽全部并提示、零题库空态；ARCHIVED 课程被闸门拦）。新建 `quiz_tests` / `quiz_test_items` 两表与评分 job 类型枚举。本票止步于"创建后进卷面页只读看卷"——作答是 03。

**Blocked by:** 01（组卷按题型抽题依赖五型题库）。

**Status:** completed

**深度参考:** `.scratch/function-plans-introduction/15-mock-test.md`（数据与迁移节、API 草案、ARCHIVED 闸门）

- [x] 新迁移建 `quiz_tests`（course_id 必填、record_id 恒 NULL、mode=MOCK、status/score/时间列）与 `quiz_test_items`（(test_id, sequence_no) 唯一、result 含 PARTIAL、ai_grade_json），扩 job_type 枚举并同步 0010 CHECK 与顶 6 处断言
- [x] 组卷 API：课程级随机抽 `generation_status=ACTIVE` 习题，DRAFT/SUPERSEDED 不进卷；题量不足抽全部并提示，零题库空态；`quiz_tests.record_id` 恒 NULL
- [x] ARCHIVED 三道闸门第一、二道生效：read blocked → 开始测试 409
- [x] 课程页第三 tab（courseTabs 联合类型 + search 校验 + zh.json 文案），历史列表抄记录列表骨架显示三态
- [x] 组卷对话框 → 创建成功跳转卷面页（独立路由），按大题分组只读展示卷子结构
- [x] 列表/详情 API（进行中测试可见已抽题目与已答状态）
- [x] pytest 与 MSW 双侧绿；api-types 重新生成
