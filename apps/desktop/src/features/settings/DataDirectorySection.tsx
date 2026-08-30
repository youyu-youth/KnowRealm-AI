import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileDown, FileUp, FolderInput, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  DataDirectoryChangeDialog,
  type ChangeDialogState,
} from "./DataDirectoryChangeDialog";
import {
  DataDirectoryExportDialog,
  type ExportDialogState,
} from "./DataDirectoryExportDialog";
import {
  DataDirectoryImportDialog,
  type ImportDialogState,
} from "./DataDirectoryImportDialog";
import {
  migrationErrorCopy,
  migrationStoppedSidecar,
} from "./migrationErrorCopy";
import {
  changeDataDirectory,
  chooseDataDirectory,
  chooseImportArchive,
  getDataDirectory,
  importFromArchive,
  listenMigrationProgress,
  openDataDirectory,
  type MigrationProgress,
} from "@/services/tauri/dataDirectory";
import {
  exitApplication,
  isDesktopLifecycleAvailable,
  relaunchApplication,
} from "@/services/tauri/lifecycle";
import { markRestartPending } from "@/services/restartPending";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function DataDirectorySection() {
  const { t } = useTranslation();
  const dataDirectory = useQuery({
    queryKey: settingsKeys.dataDirectory,
    queryFn: getDataDirectory,
  });
  const openDirectory = useMutation({
    mutationFn: () => openDataDirectory(),
  });
  const [changeState, setChangeState] = useState<ChangeDialogState | null>(
    null,
  );
  const [exportState, setExportState] = useState<ExportDialogState | null>(
    null,
  );
  const [importState, setImportState] = useState<ImportDialogState | null>(
    null,
  );
  const [pickError, setPickError] = useState<string | null>(null);
  const [importPickError, setImportPickError] = useState<string | null>(null);
  const [progress, setProgress] = useState<MigrationProgress | null>(null);
  // 空库（无课程+无记录+无档案）才显示导入兜底入口；查询失败/加载中不显示。
  const libraryState = useQuery({
    queryKey: settingsKeys.libraryState,
    queryFn: settingsApi.getLibraryState,
  });

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

  const startExport = async (includeSecrets: boolean) => {
    setExportState({ phase: "exporting" });
    try {
      const out = await settingsApi.exportDataDirectory(includeSecrets);
      setExportState({ phase: "done", fileName: out.file_name });
    } catch (error) {
      setExportState({ phase: "failed", error: errorMessage(error) });
    }
  };

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
      // 校验失败发生在停 sidecar 之前，应用仍可正常使用。
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
    // 开发构建不自动 relaunch：relaunch 出的进程会脱离 tauri CLI，
    // CLI 退出连带杀掉 vite dev server，WebView 加载 devUrl 失败将一直白屏。
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

  return (
    <div className="border-border max-w-reading mt-8 border-t pt-8">
      <h2 className="text-section font-section text-ink">
        {t("settings.dataDirectory.sectionTitle")}
      </h2>
      <p className="max-w-reading text-body text-muted-foreground">
        {t("settings.dataDirectory.sectionDescription")}
      </p>

      {dataDirectory.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.dataDirectory.loading")}
        </p>
      ) : dataDirectory.isError ? (
        <div className="mt-6">
          <Alert variant="destructive" className="w-auto">
            <AlertDescription>
              {errorMessage(dataDirectory.error)}
            </AlertDescription>
          </Alert>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => void dataDirectory.refetch()}
          >
            {t("settings.dataDirectory.retry")}
          </Button>
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          <Field>
            <FieldLabel htmlFor="data-directory-path">
              {t("settings.dataDirectory.pathLabel")}
            </FieldLabel>
            <Input
              id="data-directory-path"
              value={dataDirectory.data}
              title={dataDirectory.data}
              readOnly
            />
          </Field>
          {openDirectory.isError ? (
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>
                {errorMessage(openDirectory.error)}
              </AlertDescription>
            </Alert>
          ) : null}
          {pickError ? (
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>{pickError}</AlertDescription>
            </Alert>
          ) : null}
          {importPickError ? (
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>{importPickError}</AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={openDirectory.isPending}
              onClick={() => openDirectory.mutate()}
            >
              {openDirectory.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("settings.dataDirectory.opening")}
                />
              ) : (
                <FolderOpen data-icon="inline-start" aria-hidden="true" />
              )}
              {t("settings.dataDirectory.open")}
            </Button>
            <Button
              variant="outline"
              disabled={changeState !== null}
              onClick={() => void pickTarget()}
            >
              <FolderInput data-icon="inline-start" aria-hidden="true" />
              {t("settings.dataDirectory.change")}
            </Button>
            <Button
              variant="outline"
              disabled={exportState !== null || changeState !== null}
              onClick={() => setExportState({ phase: "confirm" })}
            >
              <FileDown data-icon="inline-start" aria-hidden="true" />
              {t("settings.dataDirectory.export")}
            </Button>
            {libraryState.data?.empty_library ? (
              <Button
                variant="outline"
                disabled={changeState !== null || importState !== null}
                onClick={() => void pickImportArchive()}
              >
                <FileUp data-icon="inline-start" aria-hidden="true" />
                {t("settings.dataDirectory.import")}
              </Button>
            ) : null}
          </div>
        </div>
      )}

      {changeState !== null ? (
        <DataDirectoryChangeDialog
          state={changeState}
          progress={progress}
          onConfirm={(target) => void startMigration(target)}
          onQuit={() => void exitApplication()}
          onDismiss={() => setChangeState(null)}
        />
      ) : null}
      {exportState !== null ? (
        <DataDirectoryExportDialog
          state={exportState}
          onConfirm={(includeSecrets) => void startExport(includeSecrets)}
          onDismiss={() => setExportState(null)}
        />
      ) : null}
      {importState !== null ? (
        <DataDirectoryImportDialog
          state={importState}
          onConfirm={(archive) => void startImport(archive)}
          onQuit={() => void exitApplication()}
          onDismiss={() => setImportState(null)}
        />
      ) : null}
    </div>
  );
}
