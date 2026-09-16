import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ChatCitation } from "@/features/chat/api/types";
import { ChatCitationList } from "@/features/chat/ChatCitationList";

type ChatCitationsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  citations: ChatCitation[];
};

/** 来源引用弹窗：展示当前对话的全部引用，条目点击行为与右栏列表一致。 */
export function ChatCitationsDialog({
  open,
  onOpenChange,
  citations,
}: ChatCitationsDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("chat.context.citations")}</DialogTitle>
          <DialogDescription>
            {t("chat.citation.dialogDescription")}
          </DialogDescription>
        </DialogHeader>
        <div className="-mx-1 max-h-[60vh] overflow-y-auto px-1">
          <ChatCitationList citations={citations} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
