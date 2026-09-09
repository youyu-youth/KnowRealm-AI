import i18next from "i18next";
import { beforeAll, describe, expect, it } from "vitest";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";
import { commandErrorCopy } from "@/services/tauri/commandErrorCopy";

// node 环境无 window 不能导入 @/i18n；用真实资源直接初始化同一 i18next 单例。
beforeAll(async () => {
  await i18next.init({
    lng: "zh",
    fallbackLng: "zh",
    resources: { zh: { translation: zh }, en: { translation: en } },
    interpolation: { escapeValue: false },
  });
});

const t = i18next.t.bind(i18next);

describe("commandErrorCopy（Rust 命令 CODE 协议码表）", () => {
  it("命中的码翻译为界面语言文案", () => {
    expect(
      commandErrorCopy("RECORDING_POWER_THREAD_UNAVAILABLE", t, "兜底"),
    ).toBe("录音电源管理不可用，请重启应用后重试。");
  });

  it("带明细的码插值 {{detail}}（EXPORT_ARCHIVE_MISSING 路径）", () => {
    expect(
      commandErrorCopy(
        "EXPORT_ARCHIVE_MISSING: C:\\archives\\x.zip",
        t,
        "兜底",
      ),
    ).toBe("导出包不存在：C:\\archives\\x.zip");
  });

  it("Error 实例与字符串 reject 两种形态都能解析", () => {
    expect(
      commandErrorCopy(new Error("RECORDING_POWER_RESULT_MISSING"), t, "兜底"),
    ).toBe("未收到录音电源管理结果，请重试。");
  });

  it("未命中的错误回退调用方兜底文案", () => {
    expect(commandErrorCopy("SOMETHING_ELSE: x", t, "兜底文案")).toBe(
      "兜底文案",
    );
  });

  it("英文界面取英文文案", async () => {
    await i18next.changeLanguage("en");
    expect(
      commandErrorCopy("EXPORT_ARCHIVE_MISSING: C:\\x", t, "fallback"),
    ).toBe("The export archive does not exist: C:\\x");
    await i18next.changeLanguage("zh");
  });
});
