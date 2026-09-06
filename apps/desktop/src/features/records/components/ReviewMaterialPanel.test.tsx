// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { ReviewMaterialPanel } from "@/features/records/components/ReviewMaterialPanel";
import { renderWithQuery } from "@/test/test-utils";

type ReviewMaterialOut = components["schemas"]["ReviewMaterialOut"];
type ReviewMaterialReadOut = components["schemas"]["ReviewMaterialReadOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const REVIEW_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}/review-material`;
const VERSIONS_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}/review-materials`;
const ADJUST_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}/review-material-adjustments`;
const CONFIRM_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}/review-material-confirmations`;

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

function materialOf(
  version: number,
  overrides: Partial<ReviewMaterialOut> = {},
) {
  return {
    id: `55555555-5555-4555-8555-${String(1_000_000_000_000 + version)}`,
    record_id: RECORD_ID,
    version_no: version,
    transcript_source_version: 1,
    generated_from_summary_id: "66666666-6666-4666-8666-666666666666",
    quick_review: version === 1 ? "## 速记一版" : "## 速记二版",
    key_list: version === 1 ? ["重点一版"] : ["重点二版"],
    mind_map_markdown: "# 大纲\n- 条目",
    status: "GENERATED",
    model: "qwen-plus",
    prompt_version: version === 1 ? "review_v1" : "review_adjust_v1",
    user_feedback: null,
    created_at: "2026-09-06T12:00:00.000000Z",
    ...overrides,
  } satisfies ReviewMaterialOut;
}

function readOf(
  material: ReviewMaterialOut | null,
  overrides: Partial<ReviewMaterialReadOut> = {},
) {
  return {
    review_material: material,
    action_required: "NONE",
    blocked_reason: null,
    active_job_id: null,
    transcript_stale: false,
    ...overrides,
  } satisfies ReviewMaterialReadOut;
}

function renderPanel() {
  return renderWithQuery(
    <ReviewMaterialPanel
      recordId={RECORD_ID}
      enabled
      onOpenSummary={vi.fn()}
    />,
  );
}

async function openWorkbench() {
  fireEvent.click(await screen.findByRole("button", { name: "确认与调整" }));
  return within(await screen.findByRole("dialog"));
}

beforeEach(() => {
  server.use(http.get(VERSIONS_URL, () => HttpResponse.json([materialOf(1)])));
});

afterEach(cleanup);

describe("ReviewMaterialPanel HITL 工作台", () => {
  it("生成完成后自动打开工作台弹窗", async () => {
    let calls = 0;
    server.use(
      http.get(REVIEW_URL, () => {
        calls += 1;
        return HttpResponse.json(
          calls >= 2
            ? readOf(materialOf(1))
            : readOf(null, { active_job_id: JOB_ID }),
        );
      }),
    );

    renderPanel();
    expect(await screen.findByText("正在生成复习资料")).toBeInTheDocument();

    const dialog = within(
      await screen.findByRole("dialog", undefined, { timeout: 8_000 }),
    );
    expect(
      dialog.getByRole("heading", { name: "速记一版" }),
    ).toBeInTheDocument();
  });

  it("确认流：弹窗内确认定版后状态更新且按钮不可再点", async () => {
    let status: ReviewMaterialOut["status"] = "GENERATED";
    let confirmCalls = 0;
    server.use(
      http.get(REVIEW_URL, () =>
        HttpResponse.json(readOf(materialOf(1, { status }))),
      ),
      http.post(CONFIRM_URL, () => {
        confirmCalls += 1;
        status = "CONFIRMED";
        return HttpResponse.json(materialOf(1, { status: "CONFIRMED" }));
      }),
    );

    renderPanel();
    const dialog = await openWorkbench();
    expect(dialog.getByText("待确认")).toBeInTheDocument();

    fireEvent.click(dialog.getByRole("button", { name: "确认定版" }));
    await waitFor(
      () =>
        expect(dialog.getByRole("button", { name: "已定版" })).toBeDisabled(),
      { timeout: 8_000 },
    );
    expect(confirmCalls).toBe(1);
  });

  it("反馈调整流：提交反馈后轮询，新版本到达刷新预览", async () => {
    let phase: "ready" | "adjusting" | "done" = "ready";
    let adjustCalls = 0;
    let adjustBody: { feedback?: string } = {};
    server.use(
      http.get(REVIEW_URL, () => {
        if (phase === "adjusting") {
          return HttpResponse.json(readOf(null, { active_job_id: JOB_ID }));
        }
        if (phase === "done") {
          return HttpResponse.json(readOf(materialOf(2)));
        }
        return HttpResponse.json(readOf(materialOf(1)));
      }),
      http.get(VERSIONS_URL, () =>
        HttpResponse.json(
          phase === "done"
            ? [materialOf(2), materialOf(1, { status: "SUPERSEDED" })]
            : [materialOf(1)],
        ),
      ),
      http.post(ADJUST_URL, async ({ request }) => {
        adjustCalls += 1;
        adjustBody = (await request.json()) as { feedback?: string };
        phase = "adjusting";
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );

    renderPanel();
    const dialog = await openWorkbench();
    fireEvent.click(dialog.getByRole("button", { name: "反馈调整" }));
    fireEvent.change(screen.getByLabelText("调整反馈"), {
      target: { value: "更简洁一些" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "提交调整" }));

    await waitFor(() => expect(adjustCalls).toBe(1));
    expect(adjustBody.feedback).toBe("更简洁一些");
    expect(
      await screen.findByText("正在按反馈调整复习资料"),
    ).toBeInTheDocument();

    phase = "done";
    await waitFor(
      () =>
        expect(
          dialog.getByRole("heading", { name: "速记二版" }),
        ).toBeInTheDocument(),
      { timeout: 8_000 },
    );
    expect(dialog.queryByRole("heading", { name: "速记一版" })).toBeNull();
  }, 10_000);

  it("编辑流：改速记与清单后保存就地生效，不换代", async () => {
    let saved = false;
    let patchBody: { quick_review?: string; key_list?: string[] } = {};
    server.use(
      http.get(REVIEW_URL, () =>
        HttpResponse.json(
          readOf(
            saved
              ? materialOf(1, {
                  quick_review: "## 手改速记",
                  key_list: ["手改重点"],
                })
              : materialOf(1),
          ),
        ),
      ),
      http.patch(REVIEW_URL, async ({ request }) => {
        patchBody = (await request.json()) as {
          quick_review?: string;
          key_list?: string[];
        };
        saved = true;
        return HttpResponse.json(
          materialOf(1, {
            quick_review: "## 手改速记",
            key_list: ["手改重点"],
          }),
        );
      }),
    );

    renderPanel();
    const dialog = await openWorkbench();
    fireEvent.click(dialog.getByRole("button", { name: "手动编辑" }));
    fireEvent.change(screen.getByLabelText("考前速记（Markdown 源码）"), {
      target: { value: "## 手改速记" },
    });
    fireEvent.change(screen.getByLabelText("重点清单第 1 条"), {
      target: { value: "手改重点" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "保存修改" }));

    await waitFor(
      () =>
        expect(
          dialog.getByRole("heading", { name: "手改速记" }),
        ).toBeInTheDocument(),
      { timeout: 8_000 },
    );
    expect(patchBody.quick_review).toBe("## 手改速记");
    expect(patchBody.key_list).toEqual(["手改重点"]);
  });

  it("版本切换：回看历史版本时只读，操作禁用", async () => {
    server.use(
      http.get(REVIEW_URL, () => HttpResponse.json(readOf(materialOf(2)))),
      http.get(VERSIONS_URL, () =>
        HttpResponse.json([
          materialOf(2),
          materialOf(1, { status: "SUPERSEDED" }),
        ]),
      ),
    );

    renderPanel();
    const dialog = await openWorkbench();
    expect(
      dialog.getByRole("heading", { name: "速记二版" }),
    ).toBeInTheDocument();

    const trigger = await dialog.findByRole("combobox", { name: "历史版本" });
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: "v1 · 已退场" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);

    await waitFor(() =>
      expect(
        dialog.getByRole("heading", { name: "速记一版" }),
      ).toBeInTheDocument(),
    );
    expect(
      dialog.getByText("正在回看历史版本；仅当前版本可确认、调整或编辑。"),
    ).toBeInTheDocument();
    for (const label of ["确认定版", "反馈调整", "手动编辑"]) {
      expect(dialog.getByRole("button", { name: label })).toBeDisabled();
    }
  });

  it("转写过期：页签与弹窗展示非阻塞提示，操作仍可用", async () => {
    server.use(
      http.get(REVIEW_URL, () =>
        HttpResponse.json(readOf(materialOf(1), { transcript_stale: true })),
      ),
    );

    const { container } = renderPanel();
    expect(
      await within(container).findByText(/转写已更新，当前复习资料基于旧转写/),
    ).toBeInTheDocument();
    expect(
      within(container).getByRole("heading", { name: "速记一版" }),
    ).toBeInTheDocument();

    const dialog = await openWorkbench();
    expect(
      dialog.getByText(/转写已更新，当前复习资料基于旧转写/),
    ).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "反馈调整" })).toBeEnabled();
  });
});
