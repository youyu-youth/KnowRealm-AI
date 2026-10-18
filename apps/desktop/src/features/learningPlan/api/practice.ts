import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";
import { learningPlanKeys } from "@/features/learningPlan/api/keys";

export type PracticeState = components["schemas"]["PracticeStateOut"];
export type RequirementsUpdate =
  components["schemas"]["PracticeRequirementsUpdate"];
export type PracticeRound = components["schemas"]["PracticeRoundOut"];
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
  prepare: (
    itemId: string,
    revision: number,
    requestId: string,
    restart?: PracticeRound,
  ) =>
    apiFetch<components["schemas"]["PracticePreparationOut"]>(
      `${base(itemId)}/preparations`,
      {
        method: "POST",
        body: JSON.stringify({
          requirements_revision: revision,
          request_id: requestId,
          ...(restart
            ? {
                expected_round_id: restart.test_id,
                expected_round_version: restart.version,
                abandon_confirmed: restart.status === "IN_PROGRESS",
              }
            : {}),
        }),
      },
    ),
  cancel: (itemId: string, preparationId: string) =>
    apiFetch<components["schemas"]["PracticePreparationOut"]>(
      `${base(itemId)}/preparations/${preparationId}/cancel`,
      { method: "POST" },
    ),
  startRound: (
    itemId: string,
    revision: number,
    requestId: string,
    preparationId?: string,
  ) =>
    apiFetch<PracticeRound>(`${base(itemId)}/rounds`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        requirements_revision: revision,
        preparation_id: preparationId,
      }),
    }),
  retryGrading: (itemId: string, testId: string, requestId: string) =>
    apiFetch<PracticeRound>(`${base(itemId)}/rounds/${testId}/retries`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    }),
};
