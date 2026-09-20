import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronsUpDown,
  FileText,
  GraduationCap,
  Library,
  MessageCircle,
  MessageSquarePlus,
  Telescope,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CoursePickerDialog } from "@/features/chat/CoursePickerDialog";
import { RecordMountDialog } from "@/features/chat/RecordMountDialog";
import { ResearchSessionDialog } from "@/features/chat/ResearchSessionDialog";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";

type NewChatButtonProps = {
  labelKey?: string;
  variant?: "default" | "outline";
};

/** 新建对话菜单：自由聊天（直达）/ 挂载记录… / 课程问答… / 全部资料（直达）/
 * 研究会话…。 */
export function NewChatButton({
  labelKey = "chat.newSession",
  variant = "default",
}: NewChatButtonProps) {
  const { t } = useTranslation();
  const [mountOpen, setMountOpen] = useState(false);
  const [courseOpen, setCourseOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const createSession = useCreateChatSession();

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant={variant} aria-label={t(labelKey)} />}
        >
          <MessageSquarePlus data-icon="inline-start" aria-hidden="true" />
          {t(labelKey)}
          <ChevronsUpDown data-icon="inline-end" aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-52">
          <DropdownMenuItem
            disabled={createSession.isPending}
            onClick={() => createSession.mutate({ mode: "ASK", scope: "FREE" })}
          >
            <MessageCircle aria-hidden="true" />
            {t("chat.newMenu.free")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setMountOpen(true)}>
            <FileText aria-hidden="true" />
            {t("chat.newMenu.record")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setCourseOpen(true)}>
            <GraduationCap aria-hidden="true" />
            {t("chat.newMenu.course")}
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={createSession.isPending}
            onClick={() => createSession.mutate({ mode: "ASK", scope: "ALL" })}
          >
            <Library aria-hidden="true" />
            {t("chat.newMenu.all")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setResearchOpen(true)}>
            <Telescope aria-hidden="true" />
            {t("chat.newMenu.research")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <RecordMountDialog open={mountOpen} onOpenChange={setMountOpen} />
      <CoursePickerDialog
        open={courseOpen}
        onOpenChange={setCourseOpen}
        pending={createSession.isPending}
        error={createSession.error?.message ?? null}
        onConfirm={(courseId) =>
          createSession.mutate({
            mode: "ASK",
            scope: "COURSE",
            course_id: courseId,
          })
        }
      />
      <ResearchSessionDialog
        open={researchOpen}
        onOpenChange={setResearchOpen}
      />
    </>
  );
}
