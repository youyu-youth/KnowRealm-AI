import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";

type RenameChatDialogProps = {
  sessionId: string;
  displayTitle: string;
  hasCustomTitle: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function RenameChatDialog({
  sessionId,
  displayTitle,
  hasCustomTitle,
  open,
  onOpenChange,
}: RenameChatDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [draftTitle, setDraftTitle] = useState("");
  const [prevOpen, setPrevOpen] = useState(open);

  // 打开瞬间初始化草稿（渲染期调整状态，替代 effect）。
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setDraftTitle(hasCustomTitle ? displayTitle : "");
  }

  const renameSession = useMutation({
    mutationFn: (nextTitle: string) => chatApi.rename(sessionId, nextTitle),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await queryClient.invalidateQueries({
        queryKey: chatKeys.detail(sessionId),
      });
      onOpenChange(false);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (renameSession.isPending) return;
    if (!nextOpen) renameSession.reset();
    onOpenChange(nextOpen);
  }

  const trimmed = draftTitle.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= 100;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("chat.rename.title")}</DialogTitle>
          <DialogDescription>{t("chat.rename.description")}</DialogDescription>
        </DialogHeader>
        {renameSession.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{renameSession.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <Field>
          <FieldLabel htmlFor="chat-rename-title">
            {t("chat.rename.label")}
          </FieldLabel>
          <Input
            id="chat-rename-title"
            value={draftTitle}
            maxLength={100}
            onChange={(event) => setDraftTitle(event.target.value)}
            autoFocus
          />
        </Field>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("chat.rename.cancel")}
          </DialogClose>
          <Button
            disabled={!canSubmit || renameSession.isPending}
            onClick={() => renameSession.mutate(trimmed)}
          >
            {renameSession.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("chat.rename.saving")}
              />
            ) : null}
            {t("chat.rename.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type DeleteChatDialogProps = {
  sessionId: string;
  title: string;
  wasActive: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function DeleteChatDialog({
  sessionId,
  title,
  wasActive,
  open,
  onOpenChange,
}: DeleteChatDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const deleteSession = useMutation({
    mutationFn: () => chatApi.delete(sessionId),
    onSuccess: async () => {
      queryClient.removeQueries({
        queryKey: chatKeys.detail(sessionId),
        exact: true,
      });
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      onOpenChange(false);
      if (wasActive) {
        await navigate({ to: "/chat" });
      }
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteSession.isPending) return;
    if (!nextOpen) deleteSession.reset();
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("chat.delete.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("chat.delete.description", { title })}
          </DialogDescription>
        </DialogHeader>
        {deleteSession.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{deleteSession.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("chat.delete.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            disabled={deleteSession.isPending}
            onClick={() => deleteSession.mutate()}
          >
            {deleteSession.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("chat.delete.deleting")}
              />
            ) : null}
            {t("chat.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
