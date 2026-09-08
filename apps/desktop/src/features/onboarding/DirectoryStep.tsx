import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FolderInput, FolderOpen, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import { DataDirectoryChangeDialog } from "@/features/settings/DataDirectoryChangeDialog";
import { DataDirectoryImportDialog } from "@/features/settings/DataDirectoryImportDialog";
import {
  useArchiveImport,
  useDataDirectoryChange,
} from "@/features/settings/useDataDirectoryFlows";
import { looksLikeOneDrivePath } from "@/features/onboarding/oneDrivePath";
import { StepHeader } from "@/features/onboarding/StepHeader";
import { getDataDirectory } from "@/services/tauri/dataDirectory";
import { exitApplication } from "@/services/tauri/lifecycle";

type Props = {
  current: number;
  onNext: () => void;
};

/** 向导②数据目录：与设置页共用同一组壳 command、迁移/导入链路（04/05）与弹窗。
 * "使用默认目录开始"=跳过；更改与导入成功后应用都会重启，向导随重启回到本步。 */
export function DirectoryStep({ current, onNext }: Props) {
  const { t } = useTranslation();
  const dataDirectory = useQuery({
    queryKey: settingsKeys.dataDirectory,
    queryFn: getDataDirectory,
  });
  const {
    changeState,
    pickError,
    progress,
    pickTarget,
    startMigration,
    dismissChange,
  } = useDataDirectoryChange();
  const {
    importState,
    importPickError,
    pickImportArchive,
    startImport,
    dismissImport,
  } = useArchiveImport();

  // 当前目录与所选更改目标都做 OneDrive 检测：目标在确认弹窗内就地警示，
  // 免得迁移+重启回到本步才看到警告。
  const suspiciousPath =
    changeState?.phase === "confirm" ? changeState.target : dataDirectory.data;
  const oneDriveSuspicious = suspiciousPath
    ? looksLikeOneDrivePath(suspiciousPath)
    : false;
  const oneDriveWarning = oneDriveSuspicious ? (
    <Alert className="bg-warning-soft text-warning-foreground w-auto">
      <TriangleAlert aria-hidden="true" />
      <AlertDescription className="text-warning-foreground">
        {t("onboarding.directory.oneDriveWarning")}
      </AlertDescription>
    </Alert>
  ) : null;
  const dialogOpen = changeState !== null || importState !== null;

  return (
    <div>
      <StepHeader
        current={current}
        title={t("onboarding.directory.title")}
        description={t("onboarding.directory.description")}
      />

      {dataDirectory.isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground mt-8 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("settings.dataDirectory.loading")}
        </p>
      ) : dataDirectory.isError ? (
        <div className="mt-8">
          <Alert variant="destructive" className="w-auto">
            <AlertDescription>{dataDirectory.error.message}</AlertDescription>
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
        <>
          {changeState?.phase !== "confirm" ? oneDriveWarning : null}
          {pickError || importPickError ? (
            <Alert variant="destructive" className="mt-8 w-auto">
              <AlertDescription>
                {pickError ?? importPickError}
              </AlertDescription>
            </Alert>
          ) : null}
          <Field className="mt-8">
            <FieldLabel htmlFor="onboarding-data-directory-path">
              {t("onboarding.directory.pathLabel")}
            </FieldLabel>
            <Input
              id="onboarding-data-directory-path"
              value={dataDirectory.data}
              title={dataDirectory.data}
              readOnly
            />
          </Field>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button disabled={dialogOpen} onClick={onNext}>
              {t("onboarding.directory.useDefault")}
            </Button>
            <Button
              variant="outline"
              disabled={dialogOpen}
              onClick={() => void pickTarget()}
            >
              <FolderInput data-icon="inline-start" aria-hidden="true" />
              {t("onboarding.directory.change")}
            </Button>
            <Button
              variant="outline"
              disabled={dialogOpen}
              onClick={() => void pickImportArchive()}
            >
              <FolderOpen data-icon="inline-start" aria-hidden="true" />
              {t("onboarding.directory.import")}
            </Button>
          </div>
        </>
      )}

      {changeState !== null ? (
        <DataDirectoryChangeDialog
          state={changeState}
          progress={progress}
          warning={oneDriveWarning ?? undefined}
          onConfirm={(target) => void startMigration(target)}
          onQuit={() => void exitApplication()}
          onDismiss={dismissChange}
        />
      ) : null}
      {importState !== null ? (
        <DataDirectoryImportDialog
          state={importState}
          onConfirm={(archive) => void startImport(archive)}
          onQuit={() => void exitApplication()}
          onDismiss={dismissImport}
        />
      ) : null}
    </div>
  );
}
