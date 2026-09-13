import { useNavigate } from "@tanstack/react-router";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatCitation } from "@/features/chat/api/types";

type ChatCitationListProps = {
  citations: ChatCitation[];
};

/** 引用来源列表：编号 + 摘录，点击跳转该记录转写页定位原文。 */
export function ChatCitationList({ citations }: ChatCitationListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  function openCitation(citation: ChatCitation) {
    void navigate({
      to: "/records/$recordId",
      params: { recordId: citation.record_id },
      search: { tab: "transcript", highlight: citation.quote },
    });
  }

  return (
    <ul
      aria-label={t("chat.citation.listLabel")}
      className="flex flex-col gap-1"
    >
      {citations.map((citation) => (
        <li key={`${citation.record_id}-${citation.index}`}>
          <button
            type="button"
            className="hover:bg-surface-subtle focus-visible:ring-ring/40 flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-start transition-colors focus-visible:ring-3"
            aria-label={t("chat.citation.entry", {
              index: citation.index,
              quote: citation.quote,
            })}
            onClick={() => openCitation(citation)}
          >
            <span className="bg-chat-accent-soft text-chat-accent mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[0.7rem] font-semibold">
              {citation.index}
            </span>
            <span className="min-w-0 flex-1">
              <span className="text-body-dense text-ink line-clamp-2 block break-words">
                {citation.quote}
              </span>
              <span className="text-label text-muted-foreground mt-0.5 flex items-center gap-1">
                <FileText className="size-3" aria-hidden="true" />
                {t("chat.citation.recordTag")}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
