/// Rust 命令用户可见错误的 Display 协议：`CODE` 或 `CODE: 明细`（仿 MigrationError）。
/// invoke 的 Err(String) 以原始字符串值 reject（不是 Error 实例），两种形态都兼容。
import type { TFunction } from "i18next";

const COMMAND_ERROR_KEYS: Record<string, string> = {
  RECORDING_POWER_THREAD_UNAVAILABLE: "recording.errors.keepAwakeUnavailable",
  RECORDING_POWER_RESULT_MISSING: "recording.errors.keepAwakeResultMissing",
  RECORDING_POWER_SYSTEM_CALL_FAILED: "recording.errors.keepAwakeSystemCall",
  EXPORT_ARCHIVE_MISSING: "settings.dataDirectory.importArchiveMissing",
};

// 码表命中的错误按界面语言返回译文（带明细时插值 {{detail}}）；未命中返回调用方的兜底文案。
export function commandErrorCopy(
  error: unknown,
  t: TFunction,
  fallback: string,
): string {
  const raw = error instanceof Error ? error.message : String(error);
  const separator = raw.indexOf(": ");
  const code = separator === -1 ? raw : raw.slice(0, separator);
  const key = COMMAND_ERROR_KEYS[code];
  if (!key) return fallback;
  return separator === -1
    ? t(key)
    : t(key, { detail: raw.slice(separator + 2) });
}
