import { SendHorizontal } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  mockCourseChatMessages,
  translateNodeName,
} from "@/features/courses/courseDetailInsights";
import { cn } from "@/lib/utils";

/** 课程对话标签页：示意消息流；发送与 CTA 统一跳转 AI 对话。 */
export function CourseChatTab({
  course,
  onOpenChat,
}: {
  course: CourseDetail;
  onOpenChat: () => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState("");
  const messages = mockCourseChatMessages(course);

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.chat.title")}
      sample
      className="mx-auto w-full max-w-3xl"
    >
      <p className="text-label text-ink-muted mt-1">
        {t("spaces.courseDetail.chat.notice")}
      </p>
      <ul className="mt-4 flex flex-col gap-3">
        {messages.map((message) => (
          <li
            key={message.id}
            className={cn(
              "flex",
              message.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            <div
              className={cn(
                "text-body-dense max-w-[85%] rounded-xl px-3.5 py-2.5 leading-relaxed",
                message.role === "user"
                  ? "bg-ink-strong text-paper"
                  : "bg-surface-subtle text-ink",
              )}
            >
              {t(message.textKey, {
                course: message.params?.course,
                first: message.params?.firstNode
                  ? translateNodeName(t, message.params.firstNode)
                  : undefined,
                second: message.params?.secondNode
                  ? translateNodeName(t, message.params.secondNode)
                  : undefined,
              })}
            </div>
          </li>
        ))}
      </ul>
      <form
        className="border-border-subtle mt-4 flex items-center gap-2 border-t pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          onOpenChat();
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t("spaces.courseDetail.chat.placeholder")}
          aria-label={t("spaces.courseDetail.chat.placeholder")}
        />
        <Button type="submit" disabled={!draft.trim()}>
          <SendHorizontal data-icon="inline-start" aria-hidden="true" />
          {t("spaces.courseDetail.chat.send")}
        </Button>
      </form>
    </SurfaceCard>
  );
}
