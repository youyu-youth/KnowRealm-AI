import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
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
  /** 可选警示（如 OneDrive 检测），仅在 confirm 阶段随目标路径展示。 */
  warning?: ReactNode;
  onConfirm: (target: string) => void;
  onQuit: () => void;
  onDismiss: () => void;
};

export function DataDirectoryChangeDialog({
  state,
  progress,
  warning,
  onConfirm,
  onQuit,
  onDismiss,
}: Props) {
  const { t } = useTranslation();
  // manualRestart 不可关闭：sidecar 已停、后端不可用，唯一正确动作是退出应用重启，
  // 放任关闭弹窗只会让用户走进各页面 Failed to fetch 的僵尸态。
  const dismissible = state.phase === "confirm" || state.phase === "failed";
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
            {warning}
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
