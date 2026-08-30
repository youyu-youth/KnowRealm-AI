import { useMutation, useQuery } from "@tanstack/react-query";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import {
  getDataDirectory,
  openDataDirectory,
} from "@/services/tauri/dataDirectory";

export function DataDirectorySection() {
  const { t } = useTranslation();
  const dataDirectory = useQuery({
    queryKey: settingsKeys.dataDirectory,
    queryFn: getDataDirectory,
  });
  const openDirectory = useMutation({
    mutationFn: (path: string) => openDataDirectory(path),
  });

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
              <AlertDescription>{openDirectory.error.message}</AlertDescription>
            </Alert>
          ) : null}
          <div>
            <Button
              variant="outline"
              disabled={openDirectory.isPending}
              onClick={() => openDirectory.mutate(dataDirectory.data)}
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
          </div>
        </div>
      )}
    </div>
  );
}
