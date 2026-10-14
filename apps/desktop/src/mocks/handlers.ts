import { http, HttpResponse } from "msw";

export const TEST_SIDECAR_URL = "http://127.0.0.1:43127";
export const TEST_LAUNCH_TOKEN = "test-launch-token";

export const preferencesPayload = {
  layout_mode: "SIDEBAR",
  theme: "SYSTEM",
  light_theme_id: "LIGHT_DEFAULT",
  dark_theme_id: "DARK_DEFAULT",
  font_scale: "M",
  language: "zh",
  timezone: null,
  close_behavior: "TRAY",
  quick_note_shortcut: "Ctrl+Alt+N",
  autostart: false,
  quiz_last_count: 5,
  last_route: null,
};

export const handlers = [
  http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
  http.get(`${TEST_SIDECAR_URL}/api/inbox`, () => HttpResponse.json([])),
  // 共享引用清单（工单 05）：课程详情共享 Tab 的默认查询兜底（空清单）。
  http.get(`${TEST_SIDECAR_URL}/api/courses/:courseId/shared-refs`, () =>
    HttpResponse.json([]),
  ),
  // Agent 授权档（工单 02）：聊天页右栏开关与直执行回执卡的默认查询兜底。
  http.get(`${TEST_SIDECAR_URL}/api/agent/auth-mode`, () =>
    HttpResponse.json({ auth_mode: "REQUEST_APPROVAL" }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/agent/operations`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
    HttpResponse.json([]),
  ),
  // 会话轮次列表（票 01）：默认无在途轮次（打开会话时的活动轮次查询兜底）。
  http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/turns`, () =>
    HttpResponse.json({ turns: [], next_before: null }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/context`, ({ params }) =>
    HttpResponse.json({
      session_id: params.id,
      version: 1,
      segment: 1,
      actual_turn_id: null,
      actual: [],
      next_estimate: null,
      next_error_code: null,
      compactions: [],
      active_summary: null,
    }),
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
  // 默认未配置搜索供应商；联网搜索开关在 chat 测试中按需覆盖为已配置。
  http.get(`${TEST_SIDECAR_URL}/api/settings/providers/web-search`, () =>
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
  http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
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
  // 课程脑图默认态：未构建 EMPTY（详情页测试按需覆盖为 REVIEW/READY 等状态）。
  http.get(`${TEST_SIDECAR_URL}/api/courses/:courseId/brain`, ({ params }) =>
    HttpResponse.json(emptyBrainSnapshot(String(params.courseId))),
  ),
  // 课程掌握度默认态：零已确认概念（详情页测试按需覆盖为真实分布与列表）。
  http.get(`${TEST_SIDECAR_URL}/api/courses/:courseId/mastery`, ({ params }) =>
    HttpResponse.json(emptyCourseMastery(String(params.courseId))),
  ),
  // 概念掌握详情默认态：数据不足空详情（测试按需覆盖为含 Evidence 的快照）。
  http.get(
    `${TEST_SIDECAR_URL}/api/courses/:courseId/mastery/concepts/:conceptId`,
    ({ params }) =>
      HttpResponse.json({
        snapshot: {
          concept_id: String(params.conceptId),
          canonical_name: "",
          description: "",
          concept_type: "TERM",
          importance: 3,
          status: "NOT_ENOUGH_DATA",
          mastery_score: null,
          confidence: null,
          evidence_count: 0,
          positive_evidence_count: 0,
          negative_evidence_count: 0,
          last_practiced_at: null,
          last_verified_at: null,
        },
        algorithm_version: "mastery_v1",
        evidences: [],
      }),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/courses/:courseId/brain/concepts`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/courses/:courseId/brain/relations`, () =>
    HttpResponse.json([]),
  ),
  http.get(
    `${TEST_SIDECAR_URL}/api/courses/:courseId/brain/concepts/:conceptId/sources`,
    ({ params }) =>
      HttpResponse.json({
        concept_id: String(params.conceptId),
        anchors: [],
        knowledge_points: [],
      }),
  ),
];

function emptyBrainSnapshot(courseId: string) {
  return {
    course_id: courseId,
    status: "EMPTY",
    concept_count: 0,
    candidate_count: 0,
    stale: false,
    active_job_id: null,
    last_built_at: null,
    graph: { nodes: [], edges: [] },
  };
}

function emptyCourseMastery(courseId: string) {
  return {
    course_id: courseId,
    confirmed_concept_count: 0,
    verified_concept_count: 0,
    coverage: 0,
    status_counts: { not_enough_data: 0, weak: 0, learning: 0, stable: 0 },
    concepts: [],
  };
}
