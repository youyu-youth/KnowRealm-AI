import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export type ImportDialogState =
  | { phase: "confirm"; archive: string }
  | { phase: "restarting" }
  | { phase: "manualRestart" }
  | { phase: "failed"; error: string };

type Props = {
  state: ImportDialogState;
  onConfirm: (archive: string) => void;
  onQuit: () => void;
  onDismiss: () => void;
};

export function DataDirectoryImportDialog({
  state,
  onConfirm,
  onQuit,
  onDismiss,
}: Props) {
  const { t } = useTranslation();
  // manualRestart 不可关闭：sidecar 已停、后端不可用，唯一正确动作是退出应用重启。
  const dismissible = state.phase === "confirm" || state.phase === "failed";

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
                {t("settings.dataDirectory.importTitle")}
              </DialogTitle>
              <DialogDescription>
                {t("settings.dataDirectory.importDescription")}
              </DialogDescription>
            </DialogHeader>
            <ul className="text-body text-muted-foreground flex list-disc flex-col gap-1 pl-5">
              <li>{t("settings.dataDirectory.importHintRestart")}</li>
            </ul>
            <Field>
              <FieldLabel htmlFor="import-archive-path">
                {t("settings.dataDirectory.importArchiveLabel")}
              </FieldLabel>
              <Input
                id="import-archive-path"
                value={state.archive}
                title={state.archive}
                readOnly
              />
            </Field>
            <DialogFooter>
              <Button variant="outline" onClick={onDismiss}>
                {t("settings.dataDirectory.cancel")}
              </Button>
              <Button onClick={() => onConfirm(state.archive)}>
                {t("settings.dataDirectory.importConfirm")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "restarting" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.importTitle")}
              </DialogTitle>
            </DialogHeader>
            <p
              role="status"
              className="text-body text-muted-foreground flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {t("settings.dataDirectory.importRestarting")}
            </p>
          </>
        ) : null}
        {state.phase === "manualRestart" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.importTitle")}
              </DialogTitle>
            </DialogHeader>
            <p role="status" className="text-body text-muted-foreground">
              {t("settings.dataDirectory.importManualRestart")}
            </p>
            <DialogFooter>
              <Button onClick={onQuit}>
                {t("settings.dataDirectory.quitApp")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "failed" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.importTitle")}
              </DialogTitle>
            </DialogHeader>
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>
                {state.error}
                <span className="mt-1 block text-xs break-all opacity-80">
                  {t("settings.dataDirectory.importFailedHint")}
                </span>
              </AlertDescription>
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
