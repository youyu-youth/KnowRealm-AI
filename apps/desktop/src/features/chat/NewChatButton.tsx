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
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CoursePickerDialog } from "@/features/chat/CoursePickerDialog";
import { RecordMountDialog } from "@/features/chat/RecordMountDialog";
import { ResearchSessionDialog } from "@/features/chat/ResearchSessionDialog";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";
import { useAgents, type AgentId } from "@/features/chat/api/agents";

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
  const agents = useAgents();
  const [agentId, setAgentId] = useState<AgentId>("general");
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
        <DropdownMenuContent align="start" className="w-72 max-w-full">
          <DropdownMenuRadioGroup
            value={agentId}
            onValueChange={(value) => {
              const selected = agents.data?.find((agent) => agent.id === value);
              if (selected) setAgentId(selected.id);
            }}
          >
            <DropdownMenuLabel>{t("chat.agents.label")}</DropdownMenuLabel>
            {(agents.data ?? []).map((agent) => (
              <DropdownMenuRadioItem
                key={agent.id}
                value={agent.id}
                closeOnClick={false}
              >
                <span className="min-w-0 whitespace-normal">
                  {t(`chat.agents.${agent.id}.name`)}
                  <span className="text-muted-foreground text-label block">
                    {t(`chat.agents.${agent.id}.description`)}
                  </span>
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          {agents.isPending ? (
            <p role="status" className="text-label px-2 py-1">
              {t("chat.loading")}
            </p>
          ) : null}
          {agents.isError ? (
            <DropdownMenuItem onClick={() => void agents.refetch()}>
              {t("chat.agents.loadError")}
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel>{t("chat.agents.scope")}</DropdownMenuLabel>
            <DropdownMenuItem
              disabled={createSession.isPending}
              onClick={() =>
                createSession.mutate({
                  agent_id: agentId,
                  mode: "ASK",
                  scope: "FREE",
                })
              }
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
              onClick={() =>
                createSession.mutate({
                  agent_id: agentId,
                  mode: "ASK",
                  scope: "ALL",
                })
              }
            >
              <Library aria-hidden="true" />
              {t("chat.newMenu.all")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setResearchOpen(true)}>
              <Telescope aria-hidden="true" />
              {t("chat.newMenu.research")}
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      {createSession.isError ? (
        <p role="alert" className="text-label text-destructive break-words">
          {createSession.error.message}
        </p>
      ) : null}
      <RecordMountDialog
        agentId={agentId}
        open={mountOpen}
        onOpenChange={setMountOpen}
      />
      <CoursePickerDialog
        open={courseOpen}
        onOpenChange={setCourseOpen}
        pending={createSession.isPending}
        error={createSession.error?.message ?? null}
        onConfirm={(courseId) =>
          createSession.mutate({
            agent_id: agentId,
            mode: "ASK",
            scope: "COURSE",
            course_id: courseId,
          })
        }
      />
      <ResearchSessionDialog
        agentId={agentId}
        open={researchOpen}
        onOpenChange={setResearchOpen}
      />
    </>
  );
}
