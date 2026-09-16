// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type CourseBrainPhase,
  useApplyReview,
  useCourseBrainSnapshot,
} from "@/features/courses/api/courseBrain";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const COURSE_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const brainUrl = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/brain`;

function snapshotPayload(
  status: CourseBrainPhase,
  overrides: Record<string, unknown> = {},
) {
  return {
    course_id: COURSE_ID,
    status,
    concept_count: 0,
    candidate_count: 0,
    stale: false,
    active_job_id: null,
    last_built_at: null,
    graph: { nodes: [], edges: [] },
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

afterEach(() => {
  server.resetHandlers();
});

describe("courseBrain hooks", () => {
  it("BUILDING 态每 2s 轮询快照，READY 后停止", async () => {
    vi.useFakeTimers();
    try {
      let calls = 0;
      server.use(
        http.get(brainUrl, () => {
          calls += 1;
          return HttpResponse.json(
            calls === 1
              ? snapshotPayload("BUILDING", { active_job_id: "job-1" })
              : snapshotPayload("READY", { concept_count: 2 }),
          );
        }),
      );
      const { result } = renderHook(() => useCourseBrainSnapshot(COURSE_ID), {
        wrapper: createWrapper(),
      });

      await vi.advanceTimersByTimeAsync(0);
      expect(result.current.data?.status).toBe("BUILDING");
      expect(result.current.data?.active_job_id).toBe("job-1");

      // 轮询计时器到期后 fetch 经微任务链结算：循环推进假计时器直到重取落地。
      for (
        let seconds = 0;
        seconds < 6 && result.current.data?.status !== "READY";
        seconds += 1
      ) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1_000);
        });
      }
      expect(result.current.data?.status).toBe("READY");
      expect(result.current.data?.concept_count).toBe(2);
      expect(calls).toBe(2);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(calls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("apply-review 成功后按 courseBrainKeys.all 失效链重取快照", async () => {
    let applied = false;
    const bodies: unknown[] = [];
    server.use(
      http.get(brainUrl, () =>
        HttpResponse.json(
          applied
            ? snapshotPayload("READY", { concept_count: 1 })
            : snapshotPayload("REVIEW", { candidate_count: 1 }),
        ),
      ),
      http.post(`${brainUrl}/apply-review`, async ({ request }) => {
        bodies.push(await request.json());
        applied = true;
        return HttpResponse.json(
          snapshotPayload("READY", { concept_count: 1 }),
        );
      }),
    );
    const wrapper = createWrapper();
    const snapshot = renderHook(() => useCourseBrainSnapshot(COURSE_ID), {
      wrapper,
    });
    const review = renderHook(() => useApplyReview(COURSE_ID), { wrapper });

    await waitFor(() =>
      expect(snapshot.result.current.data?.status).toBe("REVIEW"),
    );

    await act(async () => {
      await review.result.current.mutateAsync({
        decisions: [{ decision_type: "confirm", concept_id: "concept-1" }],
      });
    });

    await waitFor(() =>
      expect(snapshot.result.current.data?.status).toBe("READY"),
    );
    expect(snapshot.result.current.data?.concept_count).toBe(1);
    expect(bodies).toEqual([
      { decisions: [{ decision_type: "confirm", concept_id: "concept-1" }] },
    ]);
  });
});
