import type { components } from "@knowrealm/api-types";
import { ApiError, apiFetch, apiRequest } from "@/services/http/client";

export type ProfileOut = components["schemas"]["ProfileOut"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];

export const profileApi = {
  get: () => apiFetch<ProfileOut>("/api/profile"),
  save: (body: ProfileUpdate) =>
    apiFetch<ProfileOut>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // 404 = 未设置头像，按 null 处理而不是查询失败。
  getAvatar: async (): Promise<Blob | null> => {
    try {
      return await (await apiRequest("/api/profile/avatar")).blob();
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  putAvatar: (content: Uint8Array) =>
    apiRequest("/api/profile/avatar", { method: "PUT", body: content }),
  deleteAvatar: () => apiRequest("/api/profile/avatar", { method: "DELETE" }),
};
