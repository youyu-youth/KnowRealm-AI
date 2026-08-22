import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export const settingsApi = {
  grantTencentAsrConsent: () =>
    apiFetch<components["schemas"]["ExternalProcessingConsentOut"]>(
      "/api/settings/external-processing-consents/tencent-asr",
      { method: "POST" },
    ),
};
