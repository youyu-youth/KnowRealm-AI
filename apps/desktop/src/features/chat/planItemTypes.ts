/** 计划项动作类型的文案键映射（工单 03 抽共享：草案编辑器与确认卡预览共用，
 * 避免扩充 action_type 时多处改漏）。 */
export const PLAN_ITEM_TYPE_KEYS: Record<string, string> = {
  STUDY_RECORD: "chat.operationProposal.planFields.itemType.STUDY_RECORD",
  PRACTICE_QUIZ: "chat.operationProposal.planFields.itemType.PRACTICE_QUIZ",
  REVIEW_CONCEPT: "chat.operationProposal.planFields.itemType.REVIEW_CONCEPT",
  CUSTOM: "chat.operationProposal.planFields.itemType.CUSTOM",
};
