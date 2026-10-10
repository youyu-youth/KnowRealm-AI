import type { QueryClient } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  applyFontScale,
  applyTheme,
  DEFAULT_APPEARANCE,
  normalizeAppearance,
  type AppearancePreference,
} from "@/features/settings/appearance";
import { getDataDirectory } from "@/services/tauri/dataDirectory";

let currentDirectory: string | null = null;
let startupAppearance = DEFAULT_APPEARANCE;

function cacheKey(directory: string): string {
  return `knowrealm-appearance-v1:${directory}`;
}

export function readAppearanceCache(
  directory: string,
): AppearancePreference | null {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(cacheKey(directory)) ?? "null",
    );
    if (
      !value ||
      typeof value !== "object" ||
      !("version" in value) ||
      value.version !== 1 ||
      !("directory" in value) ||
      value.directory !== directory ||
      !("appearance" in value) ||
      !value.appearance ||
      typeof value.appearance !== "object" ||
      !("theme" in value.appearance) ||
      !["LIGHT", "DARK", "SYSTEM"].includes(String(value.appearance.theme))
    )
      return null;
    return normalizeAppearance(value.appearance);
  } catch {
    return null;
  }
}

export function getStartupAppearance(): AppearancePreference {
  return startupAppearance;
}

export function confirmAppearance(
  preferences: components["schemas"]["PreferencesOut"],
): void {
  const appearance = normalizeAppearance(preferences);
  startupAppearance = appearance;
  applyTheme(appearance.theme, appearance);
  applyFontScale(preferences.font_scale);
  if (!currentDirectory) return;
  try {
    localStorage.setItem(
      cacheKey(currentDirectory),
      JSON.stringify({
        version: 1,
        directory: currentDirectory,
        appearance,
      }),
    );
  } catch {
    // 派生缓存不可用不改变已经确认的本地偏好。
  }
}

// 主入口等待此 Promise 后才挂载工作区；缓存从未写入 Query 事实缓存。
export async function prepareAppearance(
  queryClient: QueryClient,
): Promise<Error | null> {
  currentDirectory = await getDataDirectory().catch(() => null);
  startupAppearance =
    (currentDirectory && readAppearanceCache(currentDirectory)) ||
    DEFAULT_APPEARANCE;
  applyTheme(startupAppearance.theme, startupAppearance);
  try {
    const preferences = await queryClient.fetchQuery({
      queryKey: settingsKeys.preferences,
      queryFn: settingsApi.getPreferences,
      staleTime: 0,
      retry: false,
    });
    confirmAppearance(preferences);
    return null;
  } catch (error) {
    return error instanceof Error ? error : new Error(String(error));
  }
}
