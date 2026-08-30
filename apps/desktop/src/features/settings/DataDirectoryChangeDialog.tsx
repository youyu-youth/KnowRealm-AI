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
import type { MigrationProgress } from "@/services/tauri/dataDirectory";
import type { MigrationErrorCopy } from "./migrationErrorCopy";

export type ChangeDialogState =
  | { phase: "confirm"; target: string }
  | { phase: "migrating"; target: string }
  | { phase: "manualRestart"; target: string }
  | { phase: "relaunching"; target: string }
  | { phase: "failed"; target: string; error: MigrationErrorCopy };

type Props = {
  state: ChangeDialogState;
  progress: MigrationProgress | null;
  onConfirm: (target: string) => void;
  onDismiss: () => void;
};

export function DataDirectoryChangeDialog({
  state,
  progress,
  onConfirm,
  onDismiss,
}: Props) {
  const { t } = useTranslation();
  const dismissible =
    state.phase === "confirm" ||
    state.phase === "failed" ||
    state.phase === "manualRestart";
  const percent =
    progress !== null && progress.totalBytes > 0
      ? Math.min(
          100,
          Math.round((progress.copiedBytes / progress.totalBytes) * 100),
        )
      : null;

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
                {t("settings.dataDirectory.changeTitle")}
              </DialogTitle>
              <DialogDescription>
                {t("settings.dataDirectory.changeDescription")}
              </DialogDescription>
            </DialogHeader>
            <ul className="text-body text-muted-foreground flex list-disc flex-col gap-1 pl-5">
              <li>{t("settings.dataDirectory.hintDuration")}</li>
              <li>{t("settings.dataDirectory.hintRestart")}</li>
              <li>{t("settings.dataDirectory.hintRecovery")}</li>
            </ul>
            <Field>
              <FieldLabel htmlFor="data-directory-target">
                {t("settings.dataDirectory.targetLabel")}
              </FieldLabel>
              <Input
                id="data-directory-target"
                value={state.target}
                title={state.target}
                readOnly
              />
            </Field>
            <DialogFooter>
              <Button variant="outline" onClick={onDismiss}>
                {t("settings.dataDirectory.cancel")}
              </Button>
              <Button onClick={() => onConfirm(state.target)}>
                {t("settings.dataDirectory.confirmChange")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "migrating" || state.phase === "relaunching" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.changeTitle")}
              </DialogTitle>
            </DialogHeader>
            <p
              role="status"
              className="text-body text-muted-foreground flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {state.phase === "relaunching"
                ? t("settings.dataDirectory.relaunching")
                : percent !== null
                  ? t("settings.dataDirectory.migratingProgress", { percent })
                  : t("settings.dataDirectory.migrating")}
            </p>
          </>
        ) : null}
        {state.phase === "manualRestart" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.changeTitle")}
              </DialogTitle>
            </DialogHeader>
            <p role="status" className="text-body text-muted-foreground">
              {t("settings.dataDirectory.manualRestart")}
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={onDismiss}>
                {t("settings.dataDirectory.close")}
              </Button>
            </DialogFooter>
          </>
        ) : null}
        {state.phase === "failed" ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {t("settings.dataDirectory.changeTitle")}
              </DialogTitle>
            </DialogHeader>
            <Alert variant="destructive" className="w-auto">
              <AlertDescription>
                {state.error.summary}
                {state.error.detail ? (
                  <span className="mt-1 block text-xs break-all opacity-80">
                    {state.error.detail}
                  </span>
                ) : null}
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
