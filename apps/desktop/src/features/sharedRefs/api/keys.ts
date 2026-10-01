// 共享引用域查询键（纯键模块，无依赖）：引用清单按课程维度缓存，增删后
// 经 all 前缀统一失效（课程问答的检索覆盖随引用变化，问答侧缓存独立不耦合）。
// candidates 是添加对话框的可引用候选（资料库清单 + 引用态过滤），同域维护。
export const sharedRefsKeys = {
  all: ["sharedRefs"] as const,
  list: (courseId: string) =>
    [...sharedRefsKeys.all, courseId, "list"] as const,
  candidates: (courseId: string) =>
    [...sharedRefsKeys.all, courseId, "candidates"] as const,
};
