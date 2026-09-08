// 界面语言的纯逻辑层：不依赖 i18n 实例，供 i18n/index.ts 初始化与组件层校正共用。
// 首帧语言 = localStorage 缓存 ?? 系统语言（navigator.language 以 zh 开头 → zh，否则 en）；
// 偏好查询成功后经 syncLanguageWithPreference 校正并写缓存，防止异步窗口闪变。

export type UiLanguage = "zh" | "en";

export const UI_LANGUAGES = ["zh", "en"] as const;

export const LANGUAGE_STORAGE_KEY = "knowrealm.uiLanguage";

export function isUiLanguage(value: string): value is UiLanguage {
  return (UI_LANGUAGES as readonly string[]).includes(value);
}

export function systemLanguage(): UiLanguage {
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function readCachedLanguage(): UiLanguage | null {
  const cached = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  return cached !== null && isUiLanguage(cached) ? cached : null;
}

export function writeCachedLanguage(language: UiLanguage): void {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
}

export function resolveInitialLanguage(): UiLanguage {
  return readCachedLanguage() ?? systemLanguage();
}

// <html lang> 用 BCP 47 区域变体，供屏幕阅读器选对读音引擎。
export function toHtmlLang(language: UiLanguage): "zh-CN" | "en-US" {
  return language === "zh" ? "zh-CN" : "en-US";
}
