import type { components } from "@knowrealm/api-types";
import {
  APPEARANCE_CHANGED_EVENT,
  appearanceSnapshot,
} from "@/hooks/useAppearanceSnapshot";

type PreferencesOut = components["schemas"]["PreferencesOut"];
export type ThemePreference = PreferencesOut["theme"];
export type FontScalePreference = PreferencesOut["font_scale"];
export type AppearancePreference = Pick<
  PreferencesOut,
  "theme" | "light_theme_id" | "dark_theme_id"
>;

// 每组独立登记；ID 来自 API 契约，预览色固定且不继承当前界面变量。
export const APPEARANCE_THEMES = {
  LIGHT: [
    {
      id: "LIGHT_DEFAULT",
      preview: ["#eff1f4", "#fafafb", "#ffffff", "#1a1c20"],
    },
    { id: "LIGHT_SAGE", preview: ["#e8eeec", "#f5f8f6", "#ffffff", "#263c35"] },
  ],
  DARK: [
    {
      id: "DARK_DEFAULT",
      preview: ["#0d0f12", "#131519", "#20242a", "#f2f4f7"],
    },
    { id: "DARK_INK", preview: ["#0e1620", "#15212e", "#213244", "#e7eef7"] },
  ],
} as const satisfies {
  LIGHT: readonly {
    id: PreferencesOut["light_theme_id"];
    preview: readonly string[];
  }[];
  DARK: readonly {
    id: PreferencesOut["dark_theme_id"];
    preview: readonly string[];
  }[];
};

export const DEFAULT_APPEARANCE: AppearancePreference = {
  theme: "SYSTEM",
  light_theme_id: APPEARANCE_THEMES.LIGHT[0].id,
  dark_theme_id: APPEARANCE_THEMES.DARK[0].id,
};

export function normalizeAppearance(value: unknown): AppearancePreference {
  const raw = value && typeof value === "object" ? value : {};
  const theme = "theme" in raw ? raw.theme : undefined;
  const light = "light_theme_id" in raw ? raw.light_theme_id : undefined;
  const dark = "dark_theme_id" in raw ? raw.dark_theme_id : undefined;
  return {
    theme: theme === "LIGHT" || theme === "DARK" ? theme : "SYSTEM",
    light_theme_id:
      APPEARANCE_THEMES.LIGHT.find((item) => item.id === light)?.id ??
      DEFAULT_APPEARANCE.light_theme_id,
    dark_theme_id:
      APPEARANCE_THEMES.DARK.find((item) => item.id === dark)?.id ??
      DEFAULT_APPEARANCE.dark_theme_id,
  };
}

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
export function applyTheme(
  theme: ThemePreference,
  selection: AppearancePreference = DEFAULT_APPEARANCE,
): void {
  const dark = theme === "DARK" || (theme === "SYSTEM" && systemPrefersDark());
  const root = document.documentElement;
  const previous = appearanceSnapshot();
  root.classList.toggle("dark", dark);
  root.classList.toggle("light", !dark);
  root.dataset.theme = dark
    ? selection.dark_theme_id
    : selection.light_theme_id;
  if (previous !== appearanceSnapshot()) {
    window.dispatchEvent(new Event(APPEARANCE_CHANGED_EVENT));
  }
}

export function applyFontScale(scale: FontScalePreference): void {
  document.documentElement.style.fontSize = FONT_SCALE_ROOT_PX[scale];
}
