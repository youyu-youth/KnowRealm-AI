import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import {
  isUiLanguage,
  resolveInitialLanguage,
  toHtmlLang,
  writeCachedLanguage,
  type UiLanguage,
} from "@/i18n/language";
import { syncTrayLanguage } from "@/services/tauri/lifecycle";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

// en 现为 zh 结构占位副本（真实翻译归工单 02）；fallbackLng=zh 兜底漏翻 key。
void i18n.use(initReactI18next).init({
  lng: resolveInitialLanguage(),
  fallbackLng: "zh",
  resources: {
    zh: { translation: zh },
    en: { translation: en },
  },
  interpolation: { escapeValue: false },
});
// init 的 lng 恒出自 resolveInitialLanguage（zh | en），守卫只为类型收窄。
document.documentElement.lang = isUiLanguage(i18n.language)
  ? toHtmlLang(i18n.language)
  : "zh-CN";

// 应用一个界面语言：切 i18n 实例 + <html lang> + 本地缓存 + 壳层托盘跟随（非桌面无操作）。
// 托盘重建失败不阻断语言切换（文案已生效，托盘旧标签等下次切换或重启自愈）。
export async function applyLanguage(language: UiLanguage): Promise<void> {
  await i18n.changeLanguage(language);
  document.documentElement.lang = toHtmlLang(language);
  writeCachedLanguage(language);
  try {
    await syncTrayLanguage(language);
  } catch (error) {
    console.warn("tray language sync failed", error);
  }
}

// 偏好到达后的校正入口：与当前语言一致只刷缓存，不一致才切换（存量升级无闪变的关键）。
// 返回 Promise 供需要确定时序的调用方（测试）等待；组件层可 void。
export function syncLanguageWithPreference(
  preferred: UiLanguage,
): Promise<void> {
  writeCachedLanguage(preferred);
  if (i18n.language === preferred) return Promise.resolve();
  return applyLanguage(preferred);
}

export default i18n;
