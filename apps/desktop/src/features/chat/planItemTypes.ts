import type { components } from "@knowrealm/api-types";

type PlanItemType = components["schemas"]["PlanItemType"];

/** 计划项动作类型的文案键映射（工单 03 抽共享：草案编辑器与确认卡预览共用，
 * 避免扩充 action_type 时多处改漏）。键域 = 生成枚举 PlanItemType——扩充
 * 枚举漏键在编译期报错（desktop-react §2：API 类型一律从 api-types 导入）。 */
export const PLAN_ITEM_TYPE_KEYS: Record<PlanItemType, string> = {
  STUDY_RECORD: "chat.operationProposal.planFields.itemType.STUDY_RECORD",
  PRACTICE_QUIZ: "chat.operationProposal.planFields.itemType.PRACTICE_QUIZ",
  REVIEW_CONCEPT: "chat.operationProposal.planFields.itemType.REVIEW_CONCEPT",
  CUSTOM: "chat.operationProposal.planFields.itemType.CUSTOM",
};

/** 草案载荷是自由 JSON（工单 03 备案手工收窄）：action_type 经本守卫收窄后
 * 才能索引 PLAN_ITEM_TYPE_KEYS。 */
export function isPlanItemType(value: string): value is PlanItemType {
  return value in PLAN_ITEM_TYPE_KEYS;
}
