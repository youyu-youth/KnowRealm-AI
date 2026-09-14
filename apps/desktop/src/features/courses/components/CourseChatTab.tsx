import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SendHorizontal } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import type { CourseDetail } from "@/features/courses/api/types";

/** 课程对话标签页：发起该课程范围的 AI 问答（创建 COURSE 会话并跳转，草稿经 ?prompt 预填）。 */
export function CourseChatTab({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);

  async function openCourseSession() {
    setPending(true);
    setError(false);
    try {
      const session = await chatApi.create({
        mode: "ASK",
        scope: "COURSE",
        course_id: course.id,
      });
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
        search: draft.trim() ? { prompt: draft.trim() } : {},
      });
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      aria-label={t("spaces.courseDetail.chat.title")}
      className="mx-auto w-full max-w-3xl"
    >
      <h3 className="text-section font-section text-ink-strong">
        {t("spaces.courseDetail.chat.title")}
      </h3>
      <p className="text-label text-ink-muted mt-1">
        {t("spaces.courseDetail.chat.notice")}
      </p>
      {error ? (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>
            {t("spaces.courseDetail.chat.error")}
          </AlertDescription>
        </Alert>
      ) : null}
      <form
        className="border-border-subtle mt-4 flex items-center gap-2 border-t pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!pending) void openCourseSession();
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("spaces.courseDetail.chat.placeholder")}
          aria-label={t("spaces.courseDetail.chat.placeholder")}
          disabled={pending}
        />
        <Button type="submit" disabled={pending || !draft.trim()}>
          {pending ? (
            <Spinner aria-label={t("spaces.courseDetail.chat.send")} />
          ) : (
            <SendHorizontal data-icon="inline-start" aria-hidden="true" />
          )}
          {t("spaces.courseDetail.chat.send")}
        </Button>
      </form>
      <Button
        variant="outline"
        className="mt-3"
        disabled={pending}
        onClick={() => void openCourseSession()}
      >
        {t("spaces.courseDetail.chat.cta", { course: course.name })}
      </Button>
    </section>
  );
}
