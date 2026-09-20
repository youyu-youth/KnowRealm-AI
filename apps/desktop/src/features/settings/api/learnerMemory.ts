import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type LearnerPreferenceOut =
  components["schemas"]["LearnerPreferenceOut"];
export type LearnerPreferenceUpdate =
  components["schemas"]["LearnerPreferenceUpdate"];
export type MemoryOutboundOut = components["schemas"]["MemoryOutboundOut"];

/** 学习画像「AI 记忆」（工单 06）：显式偏好直编、观察偏好治理、长期记忆外发开关。 */
export const learnerMemoryApi = {
  get: () => apiFetch<LearnerPreferenceOut>("/api/learner/preferences"),
  save: (body: LearnerPreferenceUpdate) =>
    apiFetch<LearnerPreferenceOut>("/api/learner/preferences", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteObserved: (key: string) =>
    apiFetch<void>(
      `/api/learner/preferences/observed/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
  setOutbound: (enabled: boolean) =>
    apiFetch<MemoryOutboundOut>("/api/learner/memory-outbound", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
};
