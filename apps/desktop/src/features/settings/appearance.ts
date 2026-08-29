import type { components } from "@knowrealm/api-types";

type PreferencesOut = components["schemas"]["PreferencesOut"];
export type ThemePreference = PreferencesOut["theme"];
export type FontScalePreference = PreferencesOut["font_scale"];

// token 全部基于 rem：改根字号即全应用等比缩放；M 为 16px 缺省档。
const FONT_SCALE_ROOT_PX: Record<FontScalePreference, string> = {
  S: "15px",
  M: "16px",
  L: "18px",
};

export function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// DARK 挂 .dark、LIGHT 挂 .light；SYSTEM 解析系统深浅色后同样落到 .dark/.light 上，
// 使 dark: 工具类与主题变量在三种模式下行为一致（JS 应用前的首帧由 theme.css 媒体查询兜底）。
export function applyTheme(theme: ThemePreference): void {
  const dark = theme === "DARK" || (theme === "SYSTEM" && systemPrefersDark());
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.classList.toggle("light", theme === "LIGHT");
}

export function applyFontScale(scale: FontScalePreference): void {
  document.documentElement.style.fontSize = FONT_SCALE_ROOT_PX[scale];
}
