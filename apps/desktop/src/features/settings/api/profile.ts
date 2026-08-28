import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type ProfileOut = components["schemas"]["ProfileOut"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];

export const profileApi = {
  get: () => apiFetch<ProfileOut>("/api/profile"),
  save: (body: ProfileUpdate) =>
    apiFetch<ProfileOut>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
