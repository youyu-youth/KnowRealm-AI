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
  http.get(`${TEST_SIDECAR_URL}/api/settings/providers/tencent-asr`, () =>
    HttpResponse.json({ provider: null }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
    HttpResponse.json({
      theme: "SYSTEM",
      font_scale: "M",
      timezone: null,
      close_behavior: "TRAY",
      quick_note_shortcut: "Ctrl+Alt+N",
      autostart: false,
      quiz_last_count: 5,
    }),
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
];
