import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { markRestartPending } from "@/services/restartPending";
import {
  changeDataDirectory,
  chooseDataDirectory,
  chooseImportArchive,
  importFromArchive,
  listenMigrationProgress,
  type MigrationProgress,
} from "@/services/tauri/dataDirectory";
import {
  isDesktopLifecycleAvailable,
  relaunchApplication,
} from "@/services/tauri/lifecycle";
import type { ChangeDialogState } from "./DataDirectoryChangeDialog";
import type { ImportDialogState } from "./DataDirectoryImportDialog";
import {
  migrationErrorCopy,
  migrationStoppedSidecar,
} from "./migrationErrorCopy";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// 04/05 的两条"停 sidecar → 重启恢复"链路（更改目录 / 导入归档），设置页与
// 首启向导（06）共用：成功返回后后端不可用，走 markRestartPending +
// 生产 relaunch / 开发 manualRestart（relaunch 在 dev 会白屏，04 已证）。

export function useDataDirectoryChange() {
  const { t } = useTranslation();
  const [changeState, setChangeState] = useState<ChangeDialogState | null>(
    null,
  );
  const [pickError, setPickError] = useState<string | null>(null);
  const [progress, setProgress] = useState<MigrationProgress | null>(null);

  useEffect(() => {
    if (!isDesktopLifecycleAvailable()) return;
    let active = true;
    let unlisten: (() => void) | undefined;
    listenMigrationProgress((payload) => setProgress(payload)).then((fn) => {
      if (active) {
        unlisten = fn;
      } else {
        fn();
      }
    });
    return () => {
      active = false;
      unlisten?.();
    };
  }, []);

  const pickTarget = async () => {
    setPickError(null);
    try {
      const target = await chooseDataDirectory(
        t("settings.dataDirectory.dialogTitle"),
      );
      if (target) {
        setChangeState({ phase: "confirm", target });
      }
    } catch (error) {
      setPickError(errorMessage(error));
    }
  };

  const startMigration = async (target: string) => {
    setProgress(null);
    setChangeState({ phase: "migrating", target });
    try {
      await changeDataDirectory(target);
    } catch (error) {
      // prepare 校验错误之外，失败同样发生在 sidecar 已停止之后：应用只能重启恢复。
      if (migrationStoppedSidecar(error)) markRestartPending();
      setChangeState({
        phase: "failed",
        target,
        error: migrationErrorCopy(error, t),
      });
      return;
    }
    // 迁移成功：sidecar 已停止且不再拉起，直到重启后端都不可用。
    markRestartPending();
    if (import.meta.env.DEV) {
      setChangeState({ phase: "manualRestart", target });
      return;
    }
    setChangeState({ phase: "relaunching", target });
    try {
      await relaunchApplication();
    } catch (error) {
      setChangeState({
        phase: "failed",
        target,
        error: migrationErrorCopy(error, t),
      });
    }
  };

  return {
    changeState,
    pickError,
    progress,
    pickTarget,
    startMigration,
    dismissChange: () => setChangeState(null),
  };
}

export function useArchiveImport() {
  const { t } = useTranslation();
  const [importState, setImportState] = useState<ImportDialogState | null>(
    null,
  );
  const [importPickError, setImportPickError] = useState<string | null>(null);

  const pickImportArchive = async () => {
    setImportPickError(null);
    try {
      const archive = await chooseImportArchive(
        t("settings.dataDirectory.importDialogTitle"),
      );
      if (archive) {
        setImportState({ phase: "confirm", archive });
      }
    } catch (error) {
      setImportPickError(errorMessage(error));
    }
  };

  const startImport = async (archive: string) => {
    setImportState({ phase: "restarting" });
    try {
      await importFromArchive(archive);
    } catch (error) {
      // 校验失败发生在停 sidecar 之前，应用仍可正常使用，可重新选择导出包重试。
      setImportState({ phase: "failed", error: errorMessage(error) });
      return;
    }
    markRestartPending();
    if (import.meta.env.DEV) {
      setImportState({ phase: "manualRestart" });
      return;
    }
    try {
      await relaunchApplication();
    } catch (error) {
      setImportState({ phase: "failed", error: errorMessage(error) });
    }
  };

  return {
    importState,
    importPickError,
    pickImportArchive,
    startImport,
    dismissImport: () => setImportState(null),
  };
}
