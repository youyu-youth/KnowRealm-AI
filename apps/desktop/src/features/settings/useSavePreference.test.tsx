// @vitest-environment jsdom
import type { components } from "@knowrealm/api-types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import "@/i18n";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import { useSavePreference } from "@/features/settings/useSavePreference";
import { preferencesPayload, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: TEST_SIDECAR_URL,
    token: "test-launch-token",
  }),
}));

it.each([false, true])(
  "保存期间开始的迟到读取不覆盖确认值（HTTP 失败对账：%s）",
  async (fail) => {
    type Preferences = components["schemas"]["PreferencesOut"];
    let current = { ...preferencesPayload, theme: "LIGHT" } as Preferences;
    let releaseWrite!: () => void;
    const writeGate = new Promise<void>((resolve) => {
      releaseWrite = resolve;
    });
    let reconciling!: () => void;
    const reconciliationStarted = new Promise<void>((resolve) => {
      reconciling = resolve;
    });
    let releaseReconciliation!: () => void;
    const reconciliationGate = new Promise<void>((resolve) => {
      releaseReconciliation = resolve;
    });
    let written = false;
    const url = `${TEST_SIDECAR_URL}/api/settings/preferences`;
    server.use(
      http.get(url, async () => {
        if (fail && written) {
          reconciling();
          await reconciliationGate;
        }
        return HttpResponse.json(current);
      }),
      http.put(url, async () => {
        await writeGate;
        current = { ...current, light_theme_id: "LIGHT_SAGE" };
        written = true;
        return fail ? HttpResponse.error() : HttpResponse.json(current);
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(settingsKeys.preferences, current);
    const view = renderHook(() => useSavePreference(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    let saving!: Promise<unknown>;
    const oldSnapshot = await settingsApi.getPreferences();
    await act(async () => {
      saving = view.result.current
        .mutateAsync({ light_theme_id: "LIGHT_SAGE" })
        .catch(() => undefined);
      await Promise.resolve();
    });
    if (fail) {
      releaseWrite();
      await reconciliationStarted;
    }
    let releaseRead!: () => void;
    const readGate = new Promise<void>((resolve) => {
      releaseRead = resolve;
    });
    const reading = readGate.then(() => oldSnapshot);
    const background = client
      .fetchQuery({
        queryKey: settingsKeys.preferences,
        queryFn: () => reading,
        staleTime: 0,
      })
      .catch(() => undefined);
    await act(async () => {
      releaseWrite();
      releaseReconciliation();
      await saving;
    });
    await act(async () => {
      releaseRead();
      await reading;
      await background;
    });
    expect(
      client.getQueryData<Preferences>(settingsKeys.preferences)
        ?.light_theme_id,
    ).toBe("LIGHT_SAGE");
    expect(document.documentElement.dataset.theme).toBe("LIGHT_SAGE");
    view.unmount();
    client.clear();
  },
);
