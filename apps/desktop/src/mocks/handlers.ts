import { http, HttpResponse } from "msw";

export const TEST_SIDECAR_URL = "http://127.0.0.1:43127";
export const TEST_LAUNCH_TOKEN = "test-launch-token";

export const handlers = [
  http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
  http.get(`${TEST_SIDECAR_URL}/api/recording-sessions`, () =>
    HttpResponse.json([]),
  ),
  http.get(`${TEST_SIDECAR_URL}/api/today/pending-summaries`, () =>
    HttpResponse.json([]),
  ),
];
