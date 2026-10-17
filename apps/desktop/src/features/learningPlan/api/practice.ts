import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";
import { learningPlanKeys } from "@/features/learningPlan/api/keys";

export type PracticeState = components["schemas"]["PracticeStateOut"];
export type RequirementsUpdate =
  components["schemas"]["PracticeRequirementsUpdate"];
export type QuestionType = components["schemas"]["QuizQuestionType"];

export const practiceKey = (itemId: string) =>
  [...learningPlanKeys.all, "practice", itemId] as const;
const base = (itemId: string) => `/api/plan-items/${itemId}/practice`;
export const practiceApi = {
  state: (itemId: string) => apiFetch<PracticeState>(base(itemId)),
  confirm: (itemId: string, body: RequirementsUpdate) =>
    apiFetch<components["schemas"]["PracticeRequirementsOut"]>(
      `${base(itemId)}/requirements`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  prepare: (itemId: string, revision: number, requestId: string) =>
    apiFetch<components["schemas"]["PracticePreparationOut"]>(
      `${base(itemId)}/preparations`,
      {
        method: "POST",
        body: JSON.stringify({
          requirements_revision: revision,
          request_id: requestId,
        }),
      },
    ),
  cancel: (itemId: string, preparationId: string) =>
    apiFetch<components["schemas"]["PracticePreparationOut"]>(
      `${base(itemId)}/preparations/${preparationId}/cancel`,
      { method: "POST" },
    ),
};
