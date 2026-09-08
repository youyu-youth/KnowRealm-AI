// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it } from "vitest";
import { applyLanguage, default as i18n } from "@/i18n";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

// 断言中途失败也不把 i18n/localStorage 残留为 en（复用 language.test.ts 的恢复模式）。
afterEach(async () => {
  if (i18n.language !== "zh") await applyLanguage("zh");
});

// 递归收集叶子 key 的全路径（与 i18next 的 "." 分隔寻址一致）。
function leafKeys(node: unknown, prefix = ""): string[] {
  if (typeof node !== "object" || node === null) return [];
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "object" && value !== null
      ? leafKeys(value, path)
      : [path];
  });
}

// i18next 复数后缀全集；英文复数 key 折算回基础 key 后再与 zh 比对。
const pluralSuffix = /_(one|other|zero|two|few|many)$/;

describe("zh / en 资源一致性", () => {
  it("递归 key 集合 diff 为空（容忍英文复数后缀）", () => {
    const zhKeys = new Set(leafKeys(zh));
    const enKeys = new Set(
      leafKeys(en).map((key) => key.replace(pluralSuffix, "")),
    );

    expect([...enKeys].filter((key) => !zhKeys.has(key))).toEqual([]);
    expect([...zhKeys].filter((key) => !enKeys.has(key))).toEqual([]);
  });

  it("en 复数 key 成对提供 _one 与 _other（孤后缀在 count≠1 时会退化回 zh 兜底）", () => {
    const enAll = new Set(leafKeys(en));
    for (const key of enAll) {
      const base = key.replace(pluralSuffix, "");
      if (base === key) continue;
      expect(enAll.has(`${base}_one`)).toBe(true);
      expect(enAll.has(`${base}_other`)).toBe(true);
    }
  });

  it("en 复数后缀 key 按英文复数规则解析，无后缀计数 key 回退基础值", async () => {
    await applyLanguage("en");

    expect(i18n.t("spaces.records.duration.hours", { count: 1 })).toBe(
      "1 hour",
    );
    expect(i18n.t("spaces.records.duration.hours", { count: 2 })).toBe(
      "2 hours",
    );
    expect(i18n.t("spaces.simulations.testTitle", { count: 15 })).toBe(
      "Mock Test with 15 Questions",
    );
    // 纯计数显示（charCount / hotWordsDescription）在 en 保留基础 key，count 传入时回退基础值。
    expect(i18n.t("settings.profile.charCount", { count: 12 })).toBe("12/200");
    expect(i18n.t("spaces.editForm.hotWordsDescription", { count: 3 })).toBe(
      "One per line; blank lines are ignored; 3 / 100 filled.",
    );
  });
});
