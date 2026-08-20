// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { documentImportApi } from "@/features/document-import/api/documentImports";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

afterEach(() => vi.unstubAllGlobals());

describe("HTTP FormData 请求", () => {
  it("保留浏览器生成 multipart 边界的权力并传递真实字段", async () => {
    let captured: RequestInit | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        captured = init;
        return new Response(
          JSON.stringify({ record_id: "record-id", job_id: "job-id" }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const file = new File(["# 第一讲"], "lecture.md", {
      type: "text/markdown",
    });

    await documentImportApi.create("course-id", file);

    expect(new Headers(captured?.headers).has("Content-Type")).toBe(false);
    expect(captured?.body).toBeInstanceOf(FormData);
    const body = captured?.body as FormData;
    expect(body.get("course_id")).toBe("course-id");
    expect(body.get("file")).toBe(file);
  });
});
