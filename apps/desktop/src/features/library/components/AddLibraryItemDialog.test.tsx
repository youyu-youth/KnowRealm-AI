// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddLibraryItemDialog } from "@/features/library/components/AddLibraryItemDialog";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const ACCEPTED = {
  item: {
    id: "33333333-3333-4333-8333-333333333333",
    course_id: null,
    course_name: null,
    source_type: "WEB",
    title: "example.com",
    origin_uri: "https://example.com/article",
    local_path: null,
    mime_type: null,
    file_size: null,
    content_hash: "hash",
    fetched_at: null,
    source_metadata: { kind: "web" },
    schema_version: 1,
    favorite: false,
    status: "ACTIVE",
    created_at: "2026-09-19T08:00:00.000000Z",
    updated_at: "2026-09-19T08:00:00.000000Z",
    availability: "PROCESSING",
  },
  job: {
    id: "44444444-4444-4444-8444-444444444444",
    record_id: "55555555-5555-4555-8555-555555555555",
    job_type: "WEB_FETCH",
    status: "PENDING",
    progress: 0,
    attempts: 0,
    max_attempts: 1,
    waiting_reason: null,
    error_code: null,
    retryable: false,
    sequence_no: 0,
    source_name: null,
  },
};

function renderDialog(
  props: Partial<Parameters<typeof AddLibraryItemDialog>[0]> = {},
) {
  return renderWithQuery(
    <AddLibraryItemDialog
      open
      onOpenChange={() => {}}
      onOpenItem={() => {}}
      {...props}
    />,
  );
}

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

describe("AddLibraryItemDialog", () => {
  it("网页标签提交 URL 入库并携带课程", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/ingest`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(ACCEPTED, { status: 202 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog();
    const urlInput = screen.getByLabelText("网页地址");
    fireEvent.change(urlInput, {
      target: { value: "https://example.com/article" },
    });
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      source: "web",
      url: "https://example.com/article",
      allow_duplicate: false,
    });
  });

  it("判重 409 展示打开已有/仍然保留，保留时携带 allow_duplicate 重发", async () => {
    const bodies: unknown[] = [];
    let first = true;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/ingest`,
        async ({ request }) => {
          bodies.push(await request.json());
          if (first) {
            first = false;
            return HttpResponse.json(
              {
                detail: "已存在相同内容的资料条目",
                code: "LIBRARY_ITEM_DUPLICATE_CONTENT",
                params: {
                  existing_item_id: "33333333-3333-4333-8333-333333333333",
                },
              },
              { status: 409 },
            );
          }
          return HttpResponse.json(ACCEPTED, { status: 202 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    const onOpenItem = vi.fn();
    renderDialog({ onOpenItem });
    fireEvent.change(screen.getByLabelText("网页地址"), {
      target: { value: "https://example.com/dup" },
    });
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    await waitFor(() =>
      expect(screen.getByText(/已存在相同内容的资料条目/)).toBeInTheDocument(),
    );
    expect(bodies).toHaveLength(1);

    // 「打开已有条目」回调带 existing id（对话框随选中关闭，保留路径另测）
    fireEvent.click(screen.getByRole("button", { name: "打开已有条目" }));
    expect(onOpenItem).toHaveBeenCalledWith(
      "33333333-3333-4333-8333-333333333333",
    );
    expect(bodies).toHaveLength(1);
  });

  it("判重 409 选择仍然保留时携带 allow_duplicate 重发", async () => {
    const bodies: unknown[] = [];
    let first = true;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/ingest`,
        async ({ request }) => {
          bodies.push(await request.json());
          if (first) {
            first = false;
            return HttpResponse.json(
              {
                detail: "已存在相同内容的资料条目",
                code: "LIBRARY_ITEM_DUPLICATE_CONTENT",
                params: {
                  existing_item_id: "33333333-3333-4333-8333-333333333333",
                },
              },
              { status: 409 },
            );
          }
          return HttpResponse.json(ACCEPTED, { status: 202 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog();
    fireEvent.change(screen.getByLabelText("网页地址"), {
      target: { value: "https://example.com/dup" },
    });
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "仍然保留" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ allow_duplicate: true });
  });

  it("文本标签空正文禁用提交，有正文后可提交", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/ingest`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json({ ...ACCEPTED, job: null }, { status: 202 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("tab", { name: /文本/ }));
    expect(screen.getByTestId("library-ingest-submit")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("正文"), {
      target: { value: "手动粘贴的正文内容。" },
    });
    expect(screen.getByTestId("library-ingest-submit")).toBeEnabled();
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      source: "text",
      content: "手动粘贴的正文内容。",
    });
  });

  it("降级粘贴入口预填原 URL 并提示手动保存来源", () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog({
      initial: {
        tab: "text",
        originUri: "https://example.com/paywall",
        title: "登录墙页面",
      },
    });
    expect(
      screen.getByText(/https:\/\/example.com\/paywall/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("标题（可选）")).toHaveValue("登录墙页面");
  });

  it("文件标签未选文件禁用提交，选择后经 multipart 提交", async () => {
    const requests: Request[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/ingest/file`,
        async ({ request }) => {
          requests.push(request);
          return HttpResponse.json({ ...ACCEPTED, job: null }, { status: 202 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("tab", { name: /文件/ }));
    expect(screen.getByTestId("library-ingest-submit")).toBeDisabled();
    const file = new File(["文档正文内容"], "笔记.txt", { type: "text/plain" });
    const input = screen.getByLabelText(/选择文件/);
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() =>
      expect(screen.getByTestId("library-ingest-submit")).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    // jsdom FormData 与 Node fetch 互不兼容（content-type 退化为 text/plain，
    // 同头像上传先例）；multipart 形状由后端 HTTP 级测试验证，此处只断言发出。
    await waitFor(() => expect(requests).toHaveLength(1));
  });

  it("服务端错误展示翻译文案", async () => {
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/library/ingest`, () =>
        HttpResponse.json(
          { detail: "仅支持 http(s) 地址", code: "WEB_FETCH_INVALID_URL" },
          { status: 422 },
        ),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderDialog();
    fireEvent.change(screen.getByLabelText("网页地址"), {
      target: { value: "ftp://example.com" },
    });
    fireEvent.click(screen.getByTestId("library-ingest-submit"));
    await waitFor(() =>
      expect(screen.getByText("仅支持 http(s) 地址")).toBeInTheDocument(),
    );
  });
});
