import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "@/mocks/server";

vi.stubGlobal("scrollTo", vi.fn());

// CI 的系统语言是 en-US：固定 navigator.language 为 zh-CN，首帧解析才不随运行环境漂移；
// 个别测试可自行改写此 stub。node 环境的纯逻辑测试无 window，跳过。
if (typeof window !== "undefined") {
  vi.spyOn(window.navigator, "language", "get").mockReturnValue("zh-CN");
}

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

// jsdom 未实现 ResizeObserver；cmdk-base（命令面板列表高度同步）依赖它。
if (
  typeof window !== "undefined" &&
  typeof window.ResizeObserver !== "function"
) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom 未实现 scrollIntoView；cmdk-base 选中项滚动定位依赖它。
if (
  typeof Element !== "undefined" &&
  Element.prototype.scrollIntoView === undefined
) {
  Element.prototype.scrollIntoView = () => undefined;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(async () => {
  cleanup();
  server.resetHandlers();
  // 语言切换测试会把实例拨到 en：恢复 zh 并清缓存，避免污染后续用例的首帧解析。
  // i18n 初始化读 window，惰性导入以免 node 环境的纯逻辑测试炸 setup。
  if (typeof window !== "undefined") {
    const { default: i18n, applyLanguage } = await import("@/i18n");
    const { LANGUAGE_STORAGE_KEY } = await import("@/i18n/language");
    window.localStorage.removeItem(LANGUAGE_STORAGE_KEY);
    document.documentElement.lang = "zh-CN";
    if (i18n.language !== "zh") await applyLanguage("zh");
  }
});
afterAll(() => server.close());
