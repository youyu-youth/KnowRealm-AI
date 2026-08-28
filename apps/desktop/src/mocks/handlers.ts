import { http, HttpResponse } from "msw";

export const TEST_SIDECAR_URL = "http://127.0.0.1:43127";
export const TEST_LAUNCH_TOKEN = "test-launch-token";

export const handlers = [
  http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
  http.get(`${TEST_SIDECAR_URL}/api/inbox`, () => HttpResponse.json([])),
  http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/messages`, () =>
    HttpResponse.json([
      {
        id: "system-row",
        role: "SYSTEM",
        content: "你是 KnowRealm 学习助手。",
        model: null,
        created_at: "2026-08-27T08:00:00.000000Z",
      },
    ]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/settings/providers/llm`, () =>
    HttpResponse.json({
      provider: {
        base_url: "https://stub.example.com/v1",
        model: "stub-chat-model",
        has_api_key: true,
        api_key_hint: null,
      },
    }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/profile`, () =>
    HttpResponse.json({
      primary_role: null,
      about_me: null,
    }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/recording-sessions`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/today/pending-summaries`, () =>
    HttpResponse.json([]),
  ),
];
