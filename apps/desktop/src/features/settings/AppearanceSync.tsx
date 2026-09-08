import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { syncLanguageWithPreference } from "@/i18n";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { applyFontScale, applyTheme } from "@/features/settings/appearance";

// 首帧按 SYSTEM 渲染，偏好到达后应用（接受一次骨架变色，不做阻塞预取）。
// 写入口（偏好分区、习题生成对话框）都走同一 query key，改动后即刻反映到这里。
// 界面语言同理：首帧用缓存/系统语言渲染，偏好到达后校正（一致只刷缓存，无闪变）。
export function AppearanceSync() {
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });
  const theme = preferences.data?.theme;
  const fontScale = preferences.data?.font_scale;
  const language = preferences.data?.language;

  useEffect(() => {
    if (theme) applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (fontScale) applyFontScale(fontScale);
  }, [fontScale]);

  useEffect(() => {
    if (language) syncLanguageWithPreference(language);
  }, [language]);

  // SYSTEM 模式下跟随系统深浅色切换。
  useEffect(() => {
    if (theme !== "SYSTEM") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => applyTheme("SYSTEM");
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, [theme]);

  return null;
}
