import { describe, expect, it } from "vitest";
import { normalizeRecordedKeys } from "./shortcutAccelerator";

describe("normalizeRecordedKeys", () => {
  it("空集合与纯修饰键集合视为未完成", () => {
    expect(normalizeRecordedKeys(new Set())).toEqual({ status: "waiting" });
    expect(normalizeRecordedKeys(new Set(["ctrl", "alt"]))).toEqual({
      status: "waiting",
    });
  });

  it("修饰键在前主键收尾时产出规范 accelerator", () => {
    expect(normalizeRecordedKeys(new Set(["ctrl", "alt", "p"]))).toEqual({
      status: "ready",
      accelerator: "Ctrl+Alt+P",
    });
    expect(normalizeRecordedKeys(new Set(["shift", "f2"]))).toEqual({
      status: "ready",
      accelerator: "Shift+F2",
    });
    expect(normalizeRecordedKeys(new Set(["alt", "arrowleft"]))).toEqual({
      status: "ready",
      accelerator: "Alt+ArrowLeft",
    });
    expect(normalizeRecordedKeys(new Set(["ctrl", "1"]))).toEqual({
      status: "ready",
      accelerator: "Ctrl+1",
    });
  });

  it("修饰键规范排序、重复修饰去重、Win 键落 Super", () => {
    expect(normalizeRecordedKeys(new Set(["shift", "ctrl", "s"]))).toEqual({
      status: "ready",
      accelerator: "Ctrl+Shift+S",
    });
    expect(normalizeRecordedKeys(new Set(["meta", "x"]))).toEqual({
      status: "ready",
      accelerator: "Super+X",
    });
  });

  it("主键在前修饰键在后不误判完成", () => {
    expect(normalizeRecordedKeys(new Set(["p"]))).toEqual({
      status: "invalid",
      reason: "missing-modifier",
    });
    expect(normalizeRecordedKeys(new Set(["p", "ctrl"]))).toEqual({
      status: "waiting",
    });
  });

  it("白名单外主键（小键盘运算符/媒体键等）拒绝", () => {
    expect(normalizeRecordedKeys(new Set(["ctrl", "add"]))).toEqual({
      status: "invalid",
      reason: "unsupported-key",
    });
    expect(normalizeRecordedKeys(new Set(["ctrl", "mediaplay"]))).toEqual({
      status: "invalid",
      reason: "unsupported-key",
    });
    expect(normalizeRecordedKeys(new Set(["ctrl", "escape"]))).toEqual({
      status: "invalid",
      reason: "unsupported-key",
    });
  });
});
