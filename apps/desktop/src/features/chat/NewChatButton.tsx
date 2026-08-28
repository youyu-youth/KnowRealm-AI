import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageSquarePlus } from "lucide-react";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";

type NewChatButtonProps = {
  labelKey?: string;
  variant?: "default" | "outline";
};

export function NewChatButton({
  labelKey = "chat.newSession",
  variant = "default",
}: NewChatButtonProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [recordId, setRecordId] = useState<string | null>(null);
  const fieldId = useId();
  const records = useQuery({
    queryKey: chatKeys.recordOptions(),
    queryFn: () => chatApi.recordOptions(),
    enabled: open,
    staleTime: 0,
  });
  const selected = records.data?.find((record) => record.id === recordId);

  const createSession = useMutation({
    mutationFn: () => chatApi.create({ mode: "ASK", record_id: recordId }),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      setOpen(false);
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
      });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (createSession.isPending) return;
        setOpen(nextOpen);
        setRecordId(null);
        createSession.reset();
      }}
    >
      <DialogTrigger render={<Button variant={variant} />}>
        <MessageSquarePlus data-icon="inline-start" aria-hidden="true" />
        {t(labelKey)}
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("chat.newSession")}</DialogTitle>
          <DialogDescription>{t("chat.mount.description")}</DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel htmlFor={fieldId}>{t("chat.mount.label")}</FieldLabel>
          <Select
            value={recordId ?? "free"}
            onValueChange={(value) =>
              setRecordId(value === "free" ? null : value)
            }
            disabled={createSession.isPending}
          >
            <SelectTrigger id={fieldId} className="w-full min-w-0">
              <SelectValue className="truncate">
                {selected?.title ?? t("chat.mount.free")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              <SelectItem value="free" className="cursor-pointer">
                {t("chat.mount.free")}
              </SelectItem>
              {(records.data ?? []).map((record) => (
                <SelectItem
                  key={record.id}
                  value={record.id}
                  disabled={!record.has_transcript}
                  className="cursor-pointer data-disabled:cursor-not-allowed"
                >
                  <span className="min-w-0 break-words whitespace-normal">
                    {record.title}
                    {record.course_id === null
                      ? ` · ${t("chat.mount.inbox")}`
                      : ""}
                    {!record.has_transcript
                      ? ` · ${t("chat.mount.notReady")}`
                      : ""}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {records.isPending ? (
          <p role="status" className="text-label text-muted-foreground">
            {t("chat.mount.loading")}
          </p>
        ) : null}
        {records.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{t("chat.mount.error")}</AlertDescription>
            <Button variant="outline" onClick={() => void records.refetch()}>
              {t("chat.retry")}
            </Button>
          </Alert>
        ) : records.data?.length === 0 ? (
          <p className="text-body text-muted-foreground">
            {t("chat.mount.empty")}
          </p>
        ) : null}
        {createSession.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{createSession.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose
            render={
              <Button variant="outline" disabled={createSession.isPending} />
            }
          >
            {t("chat.rename.cancel")}
          </DialogClose>
          <Button
            disabled={
              createSession.isPending ||
              (recordId !== null &&
                (!selected?.has_transcript ||
                  records.isError ||
                  records.isFetching))
            }
            onClick={() => createSession.mutate()}
          >
            {createSession.isPending ? (
              <Spinner aria-label={t("chat.creating")} />
            ) : null}
            {t("chat.mount.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
