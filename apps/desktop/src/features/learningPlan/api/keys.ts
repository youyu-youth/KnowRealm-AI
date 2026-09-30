// 学习计划域查询键（纯键模块，无依赖）：写操作（完成/编辑/跳过）按 all
// 前缀统一失效，今日待学清单键（today/api/keys.planItems）也挂在本前缀下，
// 今日页勾选与计划 Tab 状态经同一缓存域自动一致。
export const learningPlanKeys = {
  all: ["learningPlan"] as const,
  goals: (courseId: string) =>
    [...learningPlanKeys.all, courseId, "goals"] as const,
  versions: (courseId: string, goalId: string) =>
    [...learningPlanKeys.all, courseId, "versions", goalId] as const,
  plan: (courseId: string, planId: string) =>
    [...learningPlanKeys.all, courseId, "plan", planId] as const,
};
