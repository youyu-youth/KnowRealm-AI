import { useState } from "react";
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
import { DataDirectoryChangeDialog } from "./DataDirectoryChangeDialog";
import {
  DataDirectoryExportDialog,
  type ExportDialogState,
} from "./DataDirectoryExportDialog";
import { DataDirectoryImportDialog } from "./DataDirectoryImportDialog";
import {
  getDataDirectory,
  openDataDirectory,
} from "@/services/tauri/dataDirectory";
import { exitApplication } from "@/services/tauri/lifecycle";
import {
  useArchiveImport,
  useDataDirectoryChange,
} from "./useDataDirectoryFlows";

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
  const [exportState, setExportState] = useState<ExportDialogState | null>(
    null,
  );
  // 空库（无课程+无记录+无档案）才显示导入兜底入口；查询失败/加载中不显示。
  const libraryState = useQuery({
    queryKey: settingsKeys.libraryState,
    queryFn: settingsApi.getLibraryState,
  });

  const startExport = async (includeSecrets: boolean) => {
    setExportState({ phase: "exporting" });
    try {
      const out = await settingsApi.exportDataDirectory(includeSecrets);
      setExportState({ phase: "done", fileName: out.file_name });
    } catch (error) {
      setExportState({ phase: "failed", error: errorMessage(error) });
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
          onDismiss={dismissChange}
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
          onDismiss={dismissImport}
        />
      ) : null}
    </div>
  );
}
