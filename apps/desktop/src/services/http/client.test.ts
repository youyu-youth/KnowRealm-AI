// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { documentImportApi } from "@/features/document-import/api/documentImports";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import "@/i18n";
import { ApiError, apiFetch } from "@/services/http/client";

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

describe("ApiError 构造层错误码翻译（spec 缝隙 3）", () => {
  // 通过真实 MSW 响应走 apiRequest 完整路径；i18n 实例由 "@/i18n" 导入初始化，
  // 码表即生产 errors 命名空间。语言恢复由 setup.ts 的 afterEach 兜底。
  async function apiErrorOf(
    path: string,
    respond: () => Response,
  ): Promise<unknown> {
    server.use(http.get(`${TEST_SIDECAR_URL}${path}`, respond));
    return apiFetch(path).then(
      () => {
        throw new Error("预期请求失败");
      },
      (error: unknown) => error,
    );
  }

  it("命中码表按界面语言取译文，而非 detail 原文", async () => {
    const error = await apiErrorOf("/boom", () =>
      HttpResponse.json(
        { detail: "请先配置 LLM Provider", code: "LLM_PROVIDER_UNCONFIGURED" },
        { status: 409 },
      ),
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "LLM_PROVIDER_UNCONFIGURED",
      message: "请先配置（包含密钥的）LLM Provider",
    });
  });

  it("params 插值进译文并随错误携带（INTERNAL_ERROR 请求编号）", async () => {
    const error = await apiErrorOf("/boom", () =>
      HttpResponse.json(
        {
          detail: "服务器内部错误（请求编号：req-1）",
          code: "INTERNAL_ERROR",
          params: { request_id: "req-1" },
        },
        { status: 500 },
      ),
    );
    expect(error).toMatchObject({
      status: 500,
      code: "INTERNAL_ERROR",
      params: { request_id: "req-1" },
      message: "服务器内部错误，请稍后重试（请求编号：req-1）",
    });
  });

  it("未命中码表回显 detail 原文（未来新增码不炸）", async () => {
    const error = await apiErrorOf("/boom", () =>
      HttpResponse.json(
        { detail: "新错误的中文原文", code: "FUTURE_CODE" },
        { status: 409 },
      ),
    );
    expect(error).toMatchObject({ message: "新错误的中文原文" });
  });

  it("无 code 的错误响应回显 detail（detail-only 兼容）", async () => {
    const error = await apiErrorOf("/boom", () =>
      HttpResponse.json({ detail: "本地服务暂时不可用" }, { status: 500 }),
    );
    expect(error).toMatchObject({ message: "本地服务暂时不可用" });
  });

  it("body 非 JSON 时回退 HTTP 状态文案", async () => {
    const error = await apiErrorOf(
      "/boom",
      () => new HttpResponse("bad gateway", { status: 502 }),
    );
    expect(error).toMatchObject({ message: "Bad Gateway" });
  });

  it("英文界面取英文译文", async () => {
    const { applyLanguage } = await import("@/i18n");
    await applyLanguage("en");
    const error = await apiErrorOf("/boom", () =>
      HttpResponse.json(
        { detail: "请先配置 LLM Provider", code: "LLM_PROVIDER_UNCONFIGURED" },
        { status: 409 },
      ),
    );
    expect(error).toMatchObject({
      message: "Configure an LLM provider (including its API key) first.",
    });
  });
});
