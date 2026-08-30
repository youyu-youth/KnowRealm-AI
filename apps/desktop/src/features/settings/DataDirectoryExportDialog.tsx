import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";

export type ExportDialogState =
  | { phase: "confirm" }
  | { phase: "exporting" }
  | { phase: "done"; fileName: string }
  | { phase: "failed"; error: string };

type Props = {
  state: ExportDialogState;
  onConfirm: (includeSecrets: boolean) => void;
  onDismiss: () => void;
};

export function DataDirectoryExportDialog({
  state,
  onConfirm,
  onDismiss,
}: Props) {
  const { t } = useTranslation();
  const [includeSecrets, setIncludeSecrets] = useState(false);
  // exporting 不可关闭：模态弹窗即防重复触发的遮罩。
  const dismissible =
    state.phase === "confirm" ||
    state.phase === "done" ||
    state.phase === "failed";

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && dismissible) {
          onDismiss();
        }
      }}
    >
      <DialogContent showCloseButton={dismissible}>
        {state.phase === "confirm" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.exportTitle")}
              </DialogTitle>
              <DialogDescription>
                {t("settings.dataDirectory.exportDescription")}
              </DialogDescription>
            </DialogHeader>
            <Field orientation="horizontal">
              <Checkbox
                id="export-include-secrets"
                checked={includeSecrets}
                onCheckedChange={(checked) =>
                  setIncludeSecrets(checked === true)
                }
              />
              <FieldLabel htmlFor="export-include-secrets">
                {t("settings.dataDirectory.exportIncludeSecrets")}
              </FieldLabel>
            </Field>
            {includeSecrets ? (
              <Alert variant="destructive" className="w-auto">
                <AlertDescription>
                  {t("settings.dataDirectory.exportSecretsWarning")}
                </AlertDescription>
              </Alert>
            ) : null}
            <DialogFooter>
              <Button variant="outline" onClick={onDismiss}>
                {t("settings.dataDirectory.cancel")}
              </Button>
              <Button onClick={() => onConfirm(includeSecrets)}>
                {t("settings.dataDirectory.exportConfirm")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "exporting" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.exportTitle")}
              </DialogTitle>
            </DialogHeader>
            <p
              role="status"
              className="text-body text-muted-foreground flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {t("settings.dataDirectory.exporting")}
            </p>
          </>
        ) : null}
        {state.phase === "done" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.exportTitle")}
              </DialogTitle>
            </DialogHeader>
            <p className="text-body break-all">
              {t("settings.dataDirectory.exportDone", {
                fileName: state.fileName,
              })}
            </p>
            <DialogFooter>
              <Button onClick={onDismiss}>
                {t("settings.dataDirectory.close")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "failed" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.exportTitle")}
              </DialogTitle>
            </DialogHeader>
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>{state.error}</AlertDescription>
            </Alert>
            <DialogFooter>
              <Button variant="outline" onClick={onDismiss}>
                {t("settings.dataDirectory.close")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
