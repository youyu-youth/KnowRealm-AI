import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export const settingsApi = {
  grantTencentAsrConsent: () =>
    apiFetch<components["schemas"]["ExternalProcessingConsentOut"]>(
      "/api/settings/external-processing-consents/tencent-asr",
      { method: "POST" },
    ),
  getLlmProvider: () =>
    apiFetch<components["schemas"]["LlmProviderStateOut"]>(
      "/api/settings/providers/llm",
    ),
  updateLlmProvider: (body: components["schemas"]["LlmProviderUpdate"]) =>
    apiFetch<components["schemas"]["LlmProviderStateOut"]>(
      "/api/settings/providers/llm",
      { method: "PUT", body: JSON.stringify(body) },
    ),
  testLlmProvider: () =>
    apiFetch<components["schemas"]["LlmProviderTestOut"]>(
      "/api/settings/providers/llm/tests",
      { method: "POST" },
    ),
  getLlmConsent: () =>
    apiFetch<components["schemas"]["LlmConsentOut"]>(
      "/api/settings/external-processing-consents/llm",
    ),
  grantLlmConsent: () =>
    apiFetch<components["schemas"]["LlmConsentOut"]>(
      "/api/settings/external-processing-consents/llm",
      { method: "POST" },
    ),
  getPreferences: () =>
    apiFetch<components["schemas"]["PreferencesOut"]>(
      "/api/settings/preferences",
    ),
  updatePreferences: (
    body: components["schemas"]["PreferencesUpdate"],
  ) =>
    apiFetch<components["schemas"]["PreferencesOut"]>(
      "/api/settings/preferences",
      { method: "PUT", body: JSON.stringify(body) },
    ),
};
