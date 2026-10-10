import { useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect } from "react";
import { syncLanguageWithPreference } from "@/i18n";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import {
  applyTheme,
  normalizeAppearance,
} from "@/features/settings/appearance";
import {
  confirmAppearance,
  getStartupAppearance,
} from "@/features/settings/appearanceCache";

// 主入口已在工作区挂载前核对外观；偏好重载继续走同一应用与缓存路径。
export function AppearanceSync() {
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });
  const appearance = preferences.data
    ? normalizeAppearance(preferences.data)
    : getStartupAppearance();
  const { theme, light_theme_id, dark_theme_id } = appearance;
  const language = preferences.data?.language;

  useLayoutEffect(() => {
    if (preferences.data) confirmAppearance(preferences.data);
  }, [preferences.data]);

  useEffect(() => {
    if (language) syncLanguageWithPreference(language);
  }, [language]);

  // SYSTEM 模式下跟随系统深浅色切换。
  useEffect(() => {
    if (theme !== "SYSTEM") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () =>
      applyTheme("SYSTEM", { theme, light_theme_id, dark_theme_id });
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, [theme, light_theme_id, dark_theme_id]);

  return null;
}
