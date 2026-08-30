/// Rust 端 MigrationError 的 Display 协议：`CODE` 或 `CODE: io 明细`。
import type { TFunction } from "i18next";

const MIGRATION_ERROR_KEYS: Record<string, string> = {
  DATA_DIRECTORY_SAME: "settings.dataDirectory.errorSameDirectory",
  DATA_DIRECTORY_NESTED: "settings.dataDirectory.errorNestedDirectory",
  DATA_DIRECTORY_NOT_EMPTY: "settings.dataDirectory.errorNotEmpty",
  DATA_DIRECTORY_MIGRATION_FAILED:
    "settings.dataDirectory.errorMigrationFailed",
  DATA_DIRECTORY_CONFIG_WRITE_FAILED:
    "settings.dataDirectory.errorConfigWriteFailed",
  DATA_DIRECTORY_SOURCE_CLEANUP_FAILED:
    "settings.dataDirectory.errorSourceCleanupFailed",
};

export type MigrationErrorCopy = { summary: string; detail?: string };

export function migrationErrorCopy(
  error: unknown,
  t: TFunction,
): MigrationErrorCopy {
  const raw = error instanceof Error ? error.message : String(error);
  const separator = raw.indexOf(": ");
  const code = separator === -1 ? raw : raw.slice(0, separator);
  const key = MIGRATION_ERROR_KEYS[code];
  if (!key) {
    return { summary: raw };
  }
  return {
    summary: t(key),
    detail: separator === -1 ? undefined : raw.slice(separator + 2),
  };
}
