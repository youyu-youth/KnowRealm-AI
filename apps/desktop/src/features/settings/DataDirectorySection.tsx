import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FolderInput, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  DataDirectoryChangeDialog,
  type ChangeDialogState,
} from "./DataDirectoryChangeDialog";
import { migrationErrorCopy } from "./migrationErrorCopy";
import {
  changeDataDirectory,
  chooseDataDirectory,
  getDataDirectory,
  listenMigrationProgress,
  openDataDirectory,
  type MigrationProgress,
} from "@/services/tauri/dataDirectory";
import {
  isDesktopLifecycleAvailable,
  relaunchApplication,
} from "@/services/tauri/lifecycle";

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
      setChangeState({
        phase: "failed",
        target,
        error: migrationErrorCopy(error, t),
      });
      return;
    }
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
          </div>
        </div>
      )}

      {changeState !== null ? (
        <DataDirectoryChangeDialog
          state={changeState}
          progress={progress}
          onConfirm={(target) => void startMigration(target)}
          onDismiss={() => setChangeState(null)}
        />
      ) : null}
    </div>
  );
}
