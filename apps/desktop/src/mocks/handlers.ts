import { http, HttpResponse } from "msw";

export const TEST_SIDECAR_URL = "http://127.0.0.1:43127";
export const TEST_LAUNCH_TOKEN = "test-launch-token";

const preferencesPayload = {
  theme: "SYSTEM",
  font_scale: "M",
  timezone: null,
  close_behavior: "TRAY",
  quick_note_shortcut: "Ctrl+Alt+N",
  autostart: false,
  quiz_last_count: 5,
};

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
  http.get(`${TEST_SIDECAR_URL}/api/settings/providers/tencent-asr`, () =>
    HttpResponse.json({ provider: null }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
    HttpResponse.json(preferencesPayload),
  ),
  // 设置页服务与用量分区会拉取近 30 天用量；默认空用量避免全 App 测试误报未拦截请求。
  http.get(`${TEST_SIDECAR_URL}/api/settings/usage/llm`, () =>
    HttpResponse.json({
      items: [],
      daily: Array.from({ length: 30 }, (_, index) => ({
        date: `2026-08-${String(1 + index).padStart(2, "0")}`,
        total_tokens: 0,
        call_count: 0,
      })),
    }),
  ),
  // AppShell 的 last_route 记忆会 PUT 偏好；避免全 App 测试误报未拦截请求。
  http.put(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
    HttpResponse.json(preferencesPayload),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/profile`, () =>
    HttpResponse.json({
      nickname: null,
      primary_role: null,
      about_me: null,
    }),
  ),
  // 默认无头像；用例按需覆盖为图片响应。
  http.get(`${TEST_SIDECAR_URL}/api/profile/avatar`, () =>
    HttpResponse.json({ detail: "未设置头像" }, { status: 404 }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/recording-sessions`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/today/pending-summaries`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/today/stats`, () =>
    HttpResponse.json({
      total_learning_ms: 0,
      record_count: 0,
      course_count: 0,
      ai_summary_count: 0,
      quiz_generated_count: 0,
      quiz_answered_count: 0,
      chat_turn_count: 0,
    }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/today/stats/trend`, () =>
    HttpResponse.json([]),
  ),
];
