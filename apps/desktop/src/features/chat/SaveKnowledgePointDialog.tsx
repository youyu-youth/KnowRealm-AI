import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { appToast } from "@/components/common/appToastManager";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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
import type { ChatMessage } from "@/features/chat/api/types";
import { buildSaveDraft } from "@/features/chat/buildSaveDraft";
import {
  KnowledgePointItemForm,
  type KnowledgePointValues,
} from "@/features/records/components/KnowledgePointPanel";
import { recordKeys } from "@/features/records/api/keys";

type SaveKnowledgePointDialogProps = {
  /** 待保存的 AI 回答；null 时关闭。 */
  message: ChatMessage | null;
  onClose: () => void;
  sessionId: string;
  /** RECORD 会话的挂载记录（默认目标，可改）。 */
  defaultRecordId: string | null;
};

/**
 * 对话转知识点（对话转学习资产 V1）：把一条 AI 回答保存为目标记录的知识点。
 * 目标记录候选 = record-options 中已归类课程者（未归类记录无法建立锚点溯源）；
 * 详情预填完整正文（剥离草案 JSON、去 markdown 标记），用户编辑确认后提交。
 */
export function SaveKnowledgePointDialog({
  message,
  onClose,
  sessionId,
  defaultRecordId,
}: SaveKnowledgePointDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const open = message !== null;
  const [recordId, setRecordId] = useState<string | null>(null);
  const [noRecordError, setNoRecordError] = useState(false);
  const records = useQuery({
    queryKey: chatKeys.recordOptions(),
    queryFn: () => chatApi.recordOptions(),
    enabled: open,
    staleTime: 0,
  });
  // 锚点挂课程（source_anchors.course_id 非空）：未归类（收件箱）记录后端 409，这里直接不列。
  const fileRecords = (records.data ?? []).filter(
    (record) => record.course_id !== null && record.has_transcript,
  );
  const selected = fileRecords.find((record) => record.id === recordId);

  const save = useMutation({
    mutationFn: (values: KnowledgePointValues) =>
      chatApi.saveKnowledgePoint(sessionId, message?.id ?? "", {
        ...values,
        target_record_id: recordId ?? "",
      }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({
        queryKey: recordKeys.knowledgePoints(saved.record_id),
      });
      appToast.add({
        description: t("chat.saveKp.success", { name: saved.name }),
      });
      close();
    },
  });

  // 换一条回答打开（或关闭）时渲染期重置：目标记录回到会话挂载记录默认值。
  const currentMessageId = message?.id ?? null;
  const [lastMessageId, setLastMessageId] = useState<string | null>(null);
  if (currentMessageId !== lastMessageId) {
    setLastMessageId(currentMessageId);
    setRecordId(defaultRecordId);
    setNoRecordError(false);
    save.reset();
  }

  function close() {
    setNoRecordError(false);
    save.reset();
    onClose();
  }

  function handleSubmit(values: KnowledgePointValues) {
    if (recordId === null) {
      setNoRecordError(true);
      return;
    }
    setNoRecordError(false);
    save.mutate(values);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (save.isPending) return;
        if (nextOpen) return;
        close();
      }}
    >
      <DialogContent className="flex h-[85vh] flex-col sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("chat.saveKp.title")}</DialogTitle>
          <DialogDescription>{t("chat.saveKp.description")}</DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel>{t("chat.saveKp.targetLabel")}</FieldLabel>
          <Select
            value={recordId ?? "none"}
            onValueChange={(value) => {
              setRecordId(value === "none" ? null : value);
              setNoRecordError(false);
            }}
            disabled={save.isPending}
          >
            <SelectTrigger className="w-full min-w-0">
              <SelectValue className="truncate">
                {selected?.title ?? t("chat.saveKp.targetPlaceholder")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              {fileRecords.length === 0 ? (
                <div className="text-label text-muted-foreground px-2 py-1.5">
                  {t("chat.saveKp.targetEmpty")}
                </div>
              ) : (
                fileRecords.map((record) => (
                  <SelectItem
                    key={record.id}
                    value={record.id}
                    className="cursor-pointer"
                  >
                    <span className="min-w-0 break-words whitespace-normal">
                      {record.title}
                    </span>
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </Field>
        {noRecordError ? (
          <p role="alert" className="text-body text-destructive">
            {t("chat.saveKp.errorNoRecord")}
          </p>
        ) : null}
        {message !== null ? (
          // key 绑定消息：换一条回答打开时表单重挂载，预填草稿随之刷新。
          <KnowledgePointItemForm
            key={message.id}
            initial={{
              name: "",
              detail: buildSaveDraft(message.content),
              tags: [],
              importance: 3,
            }}
            submitLabel={t("chat.saveKp.submit")}
            pending={save.isPending}
            error={save.error}
            fillHeight
            onSubmit={handleSubmit}
            onCancel={close}
          />
        ) : null}
        {records.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{t("chat.mount.error")}</AlertDescription>
          </Alert>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
