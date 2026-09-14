import { FileText, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  isRecordCitation,
  isWebCitation,
  type ChatCitation,
} from "@/features/chat/api/types";
import { useOpenCitation } from "@/features/chat/useOpenCitation";

type ChatCitationListProps = {
  citations: ChatCitation[];
};

const citationButtonClass =
  "hover:bg-surface-subtle focus-visible:ring-ring/40 flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-start transition-colors focus-visible:ring-3";
const citationIndexBadgeClass =
  "bg-chat-accent-soft text-chat-accent mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[0.7rem] font-semibold";
const citationTagClass =
  "text-label text-muted-foreground mt-0.5 flex items-center gap-1";

function citationDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

/** 引用来源列表：record 条目点击跳转该记录转写页定位原文；web 条目点击经系统浏览器打开外链。 */
export function ChatCitationList({ citations }: ChatCitationListProps) {
  const { t } = useTranslation();

  return (
    <ul
      aria-label={t("chat.citation.listLabel")}
      className="flex flex-col gap-1"
    >
      {citations.map((citation) => (
        <CitationItem
          key={`${citation.source}-${citation.index}`}
          citation={citation}
        />
      ))}
    </ul>
  );
}

function CitationItem({ citation }: { citation: ChatCitation }) {
  const { t } = useTranslation();
  const openCitation = useOpenCitation();
  // 跨记录条目带标题快照（B2）；历史行无 title 降级为现状展示。
  const recordTitle = isRecordCitation(citation) ? citation.record_title : null;

  const main = isWebCitation(citation) ? (
    <>
      <span className="text-body-dense text-ink line-clamp-2 block break-words">
        {citation.title}
      </span>
      <span className={citationTagClass}>
        <Globe className="size-3" aria-hidden="true" />
        {citationDomain(citation.url)}
      </span>
    </>
  ) : (
    <>
      <span className="text-body-dense text-ink line-clamp-2 block break-words">
        {citation.quote}
      </span>
      <span className={citationTagClass}>
        <FileText className="size-3" aria-hidden="true" />
        {recordTitle
          ? t("chat.citation.recordFromTitle", { title: recordTitle })
          : t("chat.citation.recordTag")}
      </span>
    </>
  );

  return (
    <li>
      <button
        type="button"
        className={citationButtonClass}
        aria-label={
          isWebCitation(citation)
            ? t("chat.citation.webEntry", {
                index: citation.index,
                title: citation.title,
              })
            : recordTitle
              ? t("chat.citation.entryWithTitle", {
                  index: citation.index,
                  quote: citation.quote,
                  title: recordTitle,
                })
              : t("chat.citation.entry", {
                  index: citation.index,
                  quote: citation.quote,
                })
        }
        onClick={() => openCitation(citation)}
      >
        <span className={citationIndexBadgeClass}>{citation.index}</span>
        <span className="min-w-0 flex-1">{main}</span>
      </button>
    </li>
  );
}
