// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import { AppearanceSync } from "@/features/settings/AppearanceSync";
import {
  prepareAppearance,
  readAppearanceCache,
} from "@/features/settings/appearanceCache";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { getDataDirectory } from "@/services/tauri/dataDirectory";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));
vi.mock("@/services/tauri/dataDirectory", () => ({
  getDataDirectory: vi.fn().mockResolvedValue("test-directory"),
}));

const key = "knowrealm-appearance-v1:test-directory";
const selection = {
  theme: "LIGHT",
  light_theme_id: "LIGHT_SAGE",
  dark_theme_id: "DARK_INK",
};
const envelope = {
  version: 1,
  directory: "test-directory",
  appearance: selection,
};
const url = `${TEST_SIDECAR_URL}/api/settings/preferences`;

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("light", "dark");
  delete document.documentElement.dataset.theme;
  vi.restoreAllMocks();
  vi.mocked(getDataDirectory).mockResolvedValue("test-directory");
});

describe("启动外观与目录缓存", () => {
  it.each([
    null,
    "broken-json",
    JSON.stringify({ ...envelope, directory: "another-directory" }),
    JSON.stringify({ ...envelope, version: 0 }),
  ])("无效缓存不覆盖工作区显示前的权威偏好：%s", async (cache) => {
    if (cache) localStorage.setItem(key, cache);
    const preferences = {
      ...(await settingsApi.getPreferences()),
      ...selection,
      theme: "DARK" as const,
    };
    server.use(http.get(url, () => HttpResponse.json(preferences)));
    const client = new QueryClient();
    expect(await prepareAppearance(client)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("DARK_INK");
    expect(client.getQueryData(settingsKeys.preferences)).toEqual(preferences);
    expect(readAppearanceCache("test-directory")).toEqual({
      ...selection,
      theme: "DARK",
    });
    client.clear();
  });

  it("读取失败保留当前目录有效缓存；目录未知不使用旧目录缓存", async () => {
    localStorage.setItem(key, JSON.stringify(envelope));
    server.use(http.get(url, () => HttpResponse.error()));
    const client = new QueryClient();
    expect(await prepareAppearance(client)).toBeInstanceOf(Error);
    expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE");
    expect(client.getQueryData(settingsKeys.preferences)).toBeUndefined();
    vi.mocked(getDataDirectory).mockRejectedValue(new Error("unavailable"));
    expect(await prepareAppearance(client)).toBeInstanceOf(Error);
    expect(document.documentElement.dataset.theme).toBe("LIGHT_DEFAULT");
    client.clear();
  });

  it("缓存单组失效只回退该组；存储不可用不影响权威恢复", async () => {
    localStorage.setItem(
      key,
      JSON.stringify({
        ...envelope,
        appearance: { ...selection, light_theme_id: "DARK_INK" },
      }),
    );
    expect(readAppearanceCache("test-directory")).toEqual({
      ...selection,
      light_theme_id: "LIGHT_DEFAULT",
    });
    const preferences = {
      ...(await settingsApi.getPreferences()),
      ...selection,
    };
    server.use(http.get(url, () => HttpResponse.json(preferences)));
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("unavailable");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("unavailable");
    });
    const client = new QueryClient();
    expect(await prepareAppearance(client)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE");
    client.clear();
  });

  it("SYSTEM 恢复目标组；手动模式忽略系统事件并清理监听", async () => {
    const listeners = new Set<() => void>();
    let dark = false;
    const remove = vi.fn((_: string, listener: () => void) =>
      listeners.delete(listener),
    );
    const media = {
      get matches() {
        return dark;
      },
      addEventListener: (_: string, listener: () => void) =>
        listeners.add(listener),
      removeEventListener: remove,
    } as unknown as MediaQueryList;
    vi.spyOn(window, "matchMedia").mockReturnValue(media);
    const preferences = {
      ...(await settingsApi.getPreferences()),
      ...selection,
      theme: "SYSTEM" as const,
    };
    const client = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity } },
    });
    client.setQueryData(settingsKeys.preferences, preferences);
    const view = render(
      <QueryClientProvider client={client}>
        <AppearanceSync />
      </QueryClientProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE");
    act(() => {
      dark = true;
      listeners.forEach((listener) => listener());
    });
    expect(document.documentElement.dataset.theme).toBe("DARK_INK");
    act(() =>
      client.setQueryData(settingsKeys.preferences, {
        ...preferences,
        theme: "LIGHT",
      }),
    );
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE"),
    );
    act(() => {
      dark = true;
      listeners.forEach((listener) => listener());
    });
    expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE");
    expect(listeners.size).toBe(0);
    expect(remove).toHaveBeenCalled();
    view.unmount();
    client.clear();
  });
});
