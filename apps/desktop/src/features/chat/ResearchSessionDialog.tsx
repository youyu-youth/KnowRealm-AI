import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Globe, GraduationCap, Library } from "lucide-react";
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
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { courseKeys } from "@/features/courses/api/keys";
import { courseApi } from "@/features/courses/api/courses";
import { useCreateChatSession } from "@/features/chat/useCreateChatSession";
import { useWebSearchAvailability } from "@/features/chat/useWebSearchAvailability";
import { cn } from "@/lib/utils";

type ResearchSessionDialogProps = {
  agentId?: import("@/features/chat/api/agents").AgentId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

type ResearchScopeId = "all" | "course" | "free";

const SCOPES: {
  id: ResearchScopeId;
  labelKey: string;
  descriptionKey: string;
}[] = [
  {
    id: "all",
    labelKey: "chat.research.scope.all",
    descriptionKey: "chat.research.scope.allDesc",
  },
  {
    id: "course",
    labelKey: "chat.research.scope.course",
    descriptionKey: "chat.research.scope.courseDesc",
  },
  {
    id: "free",
    labelKey: "chat.research.scope.free",
    descriptionKey: "chat.research.scope.freeDesc",
  },
];

/** 新建研究会话弹窗（研究会话 V1）：研究问题（即标题，经 ?prompt= 预填输入框）、
 * 资料范围（默认全部资料）、联网开关（默认 ON，无搜索 key 明示降级）。 */
export function ResearchSessionDialog({
  agentId = "general",
  open,
  onOpenChange,
}: ResearchSessionDialogProps) {
  const { t } = useTranslation();
  const [question, setQuestion] = useState("");
  const [scopeId, setScopeId] = useState<ResearchScopeId>("all");
  const [courseId, setCourseId] = useState<string | null>(null);
  const [webEnabled, setWebEnabled] = useState(true);
  const createSession = useCreateChatSession();
  const webSearchAvailable = useWebSearchAvailability();
  const knowledge = agentId === "knowledge";
  const webOn = !knowledge && webEnabled && webSearchAvailable;

  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: open && scopeId === "course",
    staleTime: 0,
  });
  const courseItems = courses.data ?? [];
  // 选课有效性渲染期派生（react-hooks v7：不在 effect 内回写状态）：
  // 已选课程不在当前清单（被删/未加载完）时按未选处理。
  const selectedCourseId =
    courseId !== null && courseItems.some((course) => course.id === courseId)
      ? courseId
      : null;

  // 打开即重置：研究会话是低频新动作，不带上一场的残留。
  const resetAndClose = (next: boolean) => {
    if (next) {
      setQuestion("");
      setScopeId("all");
      setCourseId(null);
      setWebEnabled(true);
    }
    onOpenChange(next);
  };

  const trimmed = question.trim();
  const canSubmit =
    trimmed.length > 0 && (scopeId !== "course" || selectedCourseId !== null);

  const submit = () => {
    if (!canSubmit || createSession.isPending) return;
    createSession.mutate(
      {
        mode: "RESEARCH",
        agent_id: agentId,
        scope:
          scopeId === "all" ? "ALL" : scopeId === "course" ? "COURSE" : "FREE",
        ...(scopeId === "course" && selectedCourseId !== null
          ? { course_id: selectedCourseId }
          : {}),
        prompt: trimmed,
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={resetAndClose}>
      <DialogContent showCloseButton={false} className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("chat.research.dialogTitle")}</DialogTitle>
          <DialogDescription>
            {t(
              knowledge
                ? "chat.agents.readOnly"
                : "chat.research.dialogDescription",
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="research-question">
              {t("chat.research.questionLabel")}
            </Label>
            <Input
              id="research-question"
              value={question}
              placeholder={t("chat.research.questionPlaceholder")}
              maxLength={200}
              autoFocus
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submit();
                }
              }}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{t("chat.research.scopeLabel")}</Label>
            <div
              role="radiogroup"
              aria-label={t("chat.research.scopeLabel")}
              className="flex flex-col gap-1"
            >
              {SCOPES.map((scope) => {
                const selected = scope.id === scopeId;
                return (
                  <button
                    key={scope.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    disabled={createSession.isPending}
                    onClick={() => setScopeId(scope.id)}
                    className={cn(
                      "focus-visible:ring-ring/40 flex items-start gap-2.5 rounded-lg border px-3 py-2 text-start transition-colors focus-visible:ring-3",
                      selected
                        ? "border-primary bg-surface-subtle"
                        : "border-border-subtle hover:bg-surface-subtle/60",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="text-body-dense text-ink block font-medium">
                        {t(
                          knowledge && scope.id === "free"
                            ? "chat.agents.free"
                            : scope.labelKey,
                        )}
                      </span>
                      <span className="text-label text-muted-foreground mt-0.5 block">
                        {t(
                          knowledge && scope.id === "free"
                            ? "chat.agents.freeDescription"
                            : scope.descriptionKey,
                        )}
                      </span>
                    </span>
                    {scope.id === "all" ? (
                      <Library
                        className="text-ink-muted mt-1 size-4 shrink-0"
                        aria-hidden="true"
                      />
                    ) : scope.id === "course" ? (
                      <GraduationCap
                        className="text-ink-muted mt-1 size-4 shrink-0"
                        aria-hidden="true"
                      />
                    ) : (
                      <Globe
                        className="text-ink-muted mt-1 size-4 shrink-0"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {scopeId === "course" ? (
            <div className="flex flex-col gap-1.5">
              <Label>{t("chat.research.courseLabel")}</Label>
              {courses.isPending ? (
                <p
                  role="status"
                  className="text-label text-muted-foreground flex items-center gap-2 px-1 py-1.5"
                >
                  <Spinner aria-hidden="true" className="size-3" />
                  {t("chat.coursePicker.loading")}
                </p>
              ) : courses.isError ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    {t("chat.coursePicker.error")}
                  </AlertDescription>
                </Alert>
              ) : courseItems.length === 0 ? (
                <p className="text-label text-muted-foreground px-1 py-1.5">
                  {t("chat.coursePicker.empty")}
                </p>
              ) : (
                <ul
                  aria-label={t("chat.research.courseLabel")}
                  className="border-border-subtle flex max-h-40 flex-col gap-0.5 overflow-y-auto rounded-lg border p-1"
                >
                  {courseItems.map((course) => {
                    const selected = course.id === courseId;
                    return (
                      <li key={course.id}>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          disabled={createSession.isPending}
                          onClick={() => setCourseId(course.id)}
                          className={cn(
                            "focus-visible:ring-ring/40 flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-start transition-colors focus-visible:ring-3",
                            selected
                              ? "bg-surface-strong"
                              : "hover:bg-surface-subtle",
                          )}
                        >
                          <GraduationCap
                            className="text-ink-muted size-3.5 shrink-0"
                            aria-hidden="true"
                          />
                          <span className="text-body-dense text-ink min-w-0 flex-1 truncate">
                            {course.name}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : null}

          <div className="border-border-subtle flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
            <div className="min-w-0">
              <p className="text-body-dense text-ink font-medium">
                {t("chat.research.webLabel")}
              </p>
              <p className="text-label text-muted-foreground mt-0.5">
                {knowledge
                  ? t("chat.agents.readOnly")
                  : webSearchAvailable
                    ? t("chat.research.webOnHint")
                    : t("chat.research.webUnavailableHint")}
              </p>
            </div>
            <Switch
              size="sm"
              checked={webOn}
              disabled={
                knowledge || !webSearchAvailable || createSession.isPending
              }
              onCheckedChange={setWebEnabled}
              aria-label={t("chat.research.webLabel")}
            />
          </div>

          {createSession.error ? (
            <Alert variant="destructive">
              <AlertDescription>{createSession.error.message}</AlertDescription>
            </Alert>
          ) : null}
        </div>

        <DialogFooter>
          <DialogClose
            render={
              <Button variant="outline" disabled={createSession.isPending} />
            }
          >
            {t("chat.rename.cancel")}
          </DialogClose>
          <Button
            disabled={!canSubmit || createSession.isPending}
            onClick={submit}
          >
            {createSession.isPending
              ? t("chat.creating")
              : t("chat.research.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
