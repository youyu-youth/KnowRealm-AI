import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "@/mocks/server";

vi.stubGlobal("scrollTo", vi.fn());

// jsdom 未实现 URL.createObjectURL/revokeObjectURL；头像 blob 展示依赖它们。
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = (() =>
    `blob:mock-${crypto.randomUUID()}`) as typeof URL.createObjectURL;
}
if (typeof URL.revokeObjectURL !== "function") {
  URL.revokeObjectURL = (() => undefined) as typeof URL.revokeObjectURL;
}

// jsdom 未实现 matchMedia；外观偏好按 SYSTEM 解析系统深浅色时依赖它。
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
