import { describe, expect, it } from "vitest";
import { looksLikeOneDrivePath } from "./oneDrivePath";

describe("OneDrive 路径检测", () => {
  it.each([
    "C:\\Users\\tester\\OneDrive\\KnowRealm",
    "C:\\Users\\tester\\OneDrive - Contoso\\KnowRealm",
    "%OneDrive%\\KnowRealm",
    "C:\\Users\\%OneDrive%-dir\\data",
    "/home/tester/onedrive/data",
  ])("识别 OneDrive 路径：%s", (path) => {
    expect(looksLikeOneDrivePath(path)).toBe(true);
  });

  it.each([
    "C:\\Users\\tester\\KnowRealm",
    "D:\\KnowRealm",
    "/home/tester/KnowRealm",
    // 仅是名字里带 onedrive 的普通目录不算同步范围。
    "D:\\my-onedrive-backup\\data",
  ])("放行本地路径：%s", (path) => {
    expect(looksLikeOneDrivePath(path)).toBe(false);
  });
});
