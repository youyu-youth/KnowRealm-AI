// 共享引用域查询键（纯键模块，仅依赖键工厂）：引用清单按课程维度缓存，增删后
// 经 all 前缀统一失效（课程问答的检索覆盖随引用变化，问答侧缓存独立不耦合）。
// candidates 是添加对话框的可引用候选（资料库清单 + 引用态过滤，含标题搜索
// 词 q），同域维护。all 挂 library 前缀：资料生命周期（软删 / 恢复 / 永久删 /
// 归属迁移等）失效 libraryKeys.all 时同步失效引用缓存（desktop-state.md
// 「相关列表/聚合 key」——available 派生位与候选过滤都依赖条目状态）；Agent
// 确认 / 直执行 / 撤销路径在写侧显式失效（见 ChatOperationProposalCard /
// useChatStream）。
import { libraryKeys } from "@/features/library/api/keys";

export const sharedRefsKeys = {
  all: [...libraryKeys.all, "sharedRefs"] as const,
  list: (courseId: string) =>
    [...sharedRefsKeys.all, courseId, "list"] as const,
  candidates: (courseId: string, q: string) =>
    [...sharedRefsKeys.all, courseId, "candidates", q] as const,
};
