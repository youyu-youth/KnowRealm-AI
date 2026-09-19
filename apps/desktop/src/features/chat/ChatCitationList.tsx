import { useState } from "react";
import {
  BookOpen,
  BookmarkPlus,
  Check,
  FileText,
  Globe,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  isLibraryCitation,
  isRecordCitation,
  isWebCitation,
  type ChatCitation,
} from "@/features/chat/api/types";
import { useOpenCitation } from "@/features/chat/useOpenCitation";
import {
  libraryApi,
  type AgentProposalOut,
} from "@/features/library/api/library";

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

/** 引用来源列表：record 跳转记录转写定位、library 跳转资料来源预览、web 经系统浏览器打开。
 * web 来源可发起「建议保存」研究入库提案（工单 05）：创建不改事实，确认后才真实抓取。 */
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
  const libraryTitle = isLibraryCitation(citation)
    ? (citation.title ?? null)
    : null;
  const isWeb = isWebCitation(citation);

  const main = isWeb ? (
    <>
      <span className="text-body-dense text-ink line-clamp-2 block break-words">
        {citation.title}
      </span>
      <span className={citationTagClass}>
        <Globe className="size-3" aria-hidden="true" />
        {citationDomain(citation.url)}
      </span>
    </>
  ) : isLibraryCitation(citation) ? (
    <>
      <span className="text-body-dense text-ink line-clamp-2 block break-words">
        {citation.quote}
      </span>
      <span className={citationTagClass}>
        <BookOpen className="size-3" aria-hidden="true" />
        {libraryTitle
          ? t("chat.citation.libraryFromTitle", { title: libraryTitle })
          : t("chat.citation.libraryTag")}
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
          isWeb
            ? t("chat.citation.webEntry", {
                index: citation.index,
                title: citation.title,
              })
            : isLibraryCitation(citation)
              ? t("chat.citation.libraryEntry", {
                  index: citation.index,
                  quote: citation.quote,
                  title: libraryTitle ?? "",
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
      {isWeb ? (
        <ResearchSaveEntry
          // as 说明：isWeb 已收窄，但子组件形参是 string——从联合中取 web 变体的 url
          url={(citation as { url: string }).url}
          title={citation.title}
        />
      ) : null}
    </li>
  );
}

/** web 来源的就地提案卡：建议保存 → 待确认（确认/拒绝）→ 已处理。 */
function ResearchSaveEntry({ url, title }: { url: string; title: string }) {
  const { t } = useTranslation();
  const [proposal, setProposal] = useState<AgentProposalOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decided, setDecided] = useState<"APPLIED" | "REJECTED" | null>(null);

  if (decided !== null) {
    return (
      <p className="text-muted-foreground text-label px-2 pb-1">
        {decided === "APPLIED"
          ? t("chat.citation.researchSaved")
          : t("chat.citation.researchRejected")}
      </p>
    );
  }
  if (proposal === null) {
    return (
      <div className="px-2 pb-1">
        <button
          type="button"
          className="text-label text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            libraryApi
              .createProposal({
                proposal_type: "RESEARCH_INGEST",
                payload: { url, title },
              })
              .then(setProposal)
              .catch((exc: unknown) =>
                setError(exc instanceof Error ? exc.message : String(exc)),
              )
              .finally(() => setBusy(false));
          }}
        >
          <BookmarkPlus className="size-3.5" aria-hidden />
          {t("chat.citation.researchSave")}
        </button>
        {error ? (
          <p role="alert" className="text-destructive text-label">
            {error}
          </p>
        ) : null}
      </div>
    );
  }
  const decide = (accept: boolean) => {
    setBusy(true);
    const request = accept
      ? libraryApi.confirmProposal(proposal.id)
      : libraryApi.rejectProposal(proposal.id);
    request
      .then(() => setDecided(accept ? "APPLIED" : "REJECTED"))
      .catch((exc: unknown) =>
        setError(exc instanceof Error ? exc.message : String(exc)),
      )
      .finally(() => setBusy(false));
  };
  return (
    <div className="bg-surface-subtle mx-2 mb-1 flex items-center gap-2 rounded-md px-2 py-1.5">
      <span className="text-label min-w-0 flex-1 truncate">
        {t("chat.citation.researchPending")}
      </span>
      <button
        type="button"
        className="hover:bg-surface-raised rounded p-1"
        aria-label={t("chat.citation.researchAccept")}
        disabled={busy}
        onClick={() => decide(true)}
      >
        <Check className="size-3.5" aria-hidden />
      </button>
      <button
        type="button"
        className="hover:bg-surface-raised rounded p-1"
        aria-label={t("chat.citation.researchReject")}
        disabled={busy}
        onClick={() => decide(false)}
      >
        <X className="size-3.5" aria-hidden />
      </button>
      {error ? (
        <p role="alert" className="text-destructive text-label">
          {error}
        </p>
      ) : null}
    </div>
  );
}
