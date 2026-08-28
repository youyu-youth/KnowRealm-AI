import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { ChatSession } from "@/features/chat/api/types";
import { cn } from "@/lib/utils";

const chatDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
});

type ChatSessionListProps = {
  sessions: ChatSession[];
  activeSessionId?: string;
};

export function ChatSessionList({
  sessions,
  activeSessionId,
}: ChatSessionListProps) {
  const { t } = useTranslation();
  return (
    <ul aria-label={t("chat.listLabel")} className="border-border border-t">
      {sessions.map((session) => (
        <ChatSessionRow
          key={session.id}
          session={session}
          active={session.id === activeSessionId}
        />
      ))}
    </ul>
  );
}

function ChatSessionRow({
  session,
  active,
}: {
  session: ChatSession;
  active: boolean;
}) {
  const { t } = useTranslation();
  const title = session.title ?? t("chat.untitled");
  return (
    <li className="border-border flex min-w-0 items-center gap-2 border-b last:border-b-0">
      <Link
        to="/chat/$sessionId"
        params={{ sessionId: session.id }}
        className={cn(
          "hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 min-w-0 flex-1 rounded-sm px-2 py-4 transition-colors focus-visible:ring-3",
          active && "bg-surface-subtle",
        )}
      >
        <span
          className="text-body font-section text-ink block truncate"
          title={title}
        >
          {title}
        </span>
        <time
          dateTime={session.updated_at}
          className="text-label text-muted-foreground mt-1 block"
        >
          {t("chat.updatedAt", {
            time: chatDateFormatter.format(new Date(session.updated_at)),
          })}
        </time>
      </Link>
      <RenameChatDialog sessionId={session.id} title={title} />
      <DeleteChatDialog
        sessionId={session.id}
        title={title}
        wasActive={active}
      />
    </li>
  );
}

function RenameChatDialog({
  sessionId,
  title,
}: {
  sessionId: string;
  title: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");

  const renameSession = useMutation({
    mutationFn: (nextTitle: string) => chatApi.rename(sessionId, nextTitle),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      queryClient.removeQueries({
        queryKey: chatKeys.detail(sessionId),
        exact: true,
      });
      setOpen(false);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (renameSession.isPending) return;
    if (!nextOpen) renameSession.reset();
    setDraftTitle(nextOpen ? (title === t("chat.untitled") ? "" : title) : "");
    setOpen(nextOpen);
  }

  const trimmed = draftTitle.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= 100;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("chat.rename.action", { title })}
          />
        }
      >
        <Pencil aria-hidden="true" />
      </DialogTrigger>
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

function DeleteChatDialog({
  sessionId,
  title,
  wasActive,
}: {
  sessionId: string;
  title: string;
  wasActive: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const deleteSession = useMutation({
    mutationFn: () => chatApi.delete(sessionId),
    onSuccess: async () => {
      queryClient.removeQueries({
        queryKey: chatKeys.detail(sessionId),
        exact: true,
      });
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      setOpen(false);
      if (wasActive) {
        await navigate({ to: "/chat" });
      }
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteSession.isPending) return;
    if (!nextOpen) deleteSession.reset();
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("chat.delete.action", { title })}
          />
        }
      >
        <Trash2 aria-hidden="true" />
      </DialogTrigger>
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
