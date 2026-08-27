import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type TextCaptureAccepted = components["schemas"]["TextCaptureAccepted"];

export type TextCaptureMode = "QUICK_NOTE" | "PASTE";

export type TextCaptureRequest = {
  capture_type: TextCaptureMode;
  content: string;
  course_id?: string | null;
};

export const textCaptureApi = {
  create(body: TextCaptureRequest) {
    return apiFetch<TextCaptureAccepted>("/api/text-captures", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
