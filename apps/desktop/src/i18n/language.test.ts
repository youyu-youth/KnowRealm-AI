// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyLanguage,
  default as i18n,
  syncLanguageWithPreference,
} from "@/i18n";
import {
  LANGUAGE_STORAGE_KEY,
  resolveInitialLanguage,
  systemLanguage,
  toHtmlLang,
} from "@/i18n/language";

// setup.ts 已把 navigator.language stub 为 zh-CN；个别用例就地改写返回值。
function stubSystemLanguage(tag: string) {
  vi.spyOn(window.navigator, "language", "get").mockReturnValue(tag);
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(async () => {
  if (i18n.language !== "zh") await applyLanguage("zh");
});

describe("首帧语言解析", () => {
  it("无缓存时跟随系统语言（zh 开头 → zh，否则 en）", () => {
    stubSystemLanguage("zh-CN");
    expect(systemLanguage()).toBe("zh");
    expect(resolveInitialLanguage()).toBe("zh");

    stubSystemLanguage("en-US");
    expect(systemLanguage()).toBe("en");
    expect(resolveInitialLanguage()).toBe("en");
  });

  it("缓存命中优先于系统语言（英文系统上的存量中文选择不被系统翻转）", () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "zh");
    stubSystemLanguage("en-US");
    expect(resolveInitialLanguage()).toBe("zh");
  });

  it("缓存值非法时按未命中处理", () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "fr");
    stubSystemLanguage("zh-CN");
    expect(resolveInitialLanguage()).toBe("zh");
  });

  it("<html lang> 用 BCP 47 区域变体", () => {
    expect(toHtmlLang("zh")).toBe("zh-CN");
    expect(toHtmlLang("en")).toBe("en-US");
  });
});

describe("语言应用与偏好校正", () => {
  it("applyLanguage 切换 i18n 实例、<html lang> 并写缓存", async () => {
    await applyLanguage("en");

    expect(i18n.language).toBe("en");
    expect(document.documentElement.lang).toBe("en-US");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("偏好与当前语言一致时只刷缓存，语言不动（存量 zh 用户无闪变）", () => {
    stubSystemLanguage("zh-CN");
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "en");

    syncLanguageWithPreference("zh");

    expect(i18n.language).toBe("zh");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("zh");
  });

  it("偏好与当前语言不一致时校正回偏好（首帧系统语言 ≠ 偏好的迁移路径）", async () => {
    await applyLanguage("en");
    stubSystemLanguage("en-US");

    await syncLanguageWithPreference("zh");

    expect(i18n.language).toBe("zh");
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("zh");
  });
});
