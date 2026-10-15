import { LearningResumeLink } from "@/features/today/components/LearningResumeLink";
import { parseResumeHref } from "@/features/today/resumeTarget";
import type { AnchorHTMLAttributes } from "react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { code } from "@streamdown/code";
import { cjk } from "@streamdown/cjk";
import { math } from "@streamdown/math";
import { Streamdown, defaultRemarkPlugins, type Components } from "streamdown";
import { isWebCitation, type ChatCitation } from "@/features/chat/api/types";
import { useOpenCitation } from "@/features/chat/useOpenCitation";

const CHAT_PLUGINS = { code, cjk, math };
const CHAT_SHIKI_THEME: [string, string] = ["github-light", "github-dark"];

type ChatMarkdownProps = {
  content: string;
  citations: ChatCitation[];
  /** true = 正在流式生成：允许不完整 Markdown 与逐字动画。 */
  streaming?: boolean;
};

/**
 * 回答正文渲染：Streamdown 处理流式 Markdown（代码高亮、CJK 换行、公式）。
 * 正文 [n] 角标经 remark 插件转成 #citation-n 链接，再在 components.a 中
 * 渲染为可点击角标；没有对应引用时回退纯文本（与后端解析规则一致）。
 */
export function ChatMarkdown({
  content,
  citations,
  streaming = false,
}: ChatMarkdownProps) {
  const { t } = useTranslation();
  const openCitation = useOpenCitation();

  const components = useMemo<Components>(() => {
    const citationMap = new Map(
      citations.map((citation) => [citation.index, citation]),
    );
    return {
      a: ({ href, children }: AnchorHTMLAttributes<HTMLAnchorElement>) => {
        if (typeof href === "string" && href.startsWith("#citation-")) {
          const index = Number(href.slice("#citation-".length));
          const citation = Number.isInteger(index)
            ? citationMap.get(index)
            : undefined;
          if (citation === undefined) return <>{children}</>;
          return (
            <button
              type="button"
              className={markerButtonClass}
              aria-label={
                isWebCitation(citation)
                  ? t("chat.citation.jumpWeb", { index: citation.index })
                  : t("chat.citation.jump", { index: citation.index })
              }
              onClick={() => openCitation(citation)}
            >
              {children}
            </button>
          );
        }
        const target = typeof href === "string" ? parseResumeHref(href) : null;
        if (target)
          return (
            <LearningResumeLink target={target}>{children}</LearningResumeLink>
          );
        if (href?.startsWith("/")) return <>{children}</>;
        return <a href={href}>{children}</a>;
      },
    };
  }, [citations, openCitation, t]);

  return (
    <Streamdown
      mode={streaming ? "streaming" : "static"}
      isAnimating={streaming}
      animated={streaming}
      caret="block"
      plugins={CHAT_PLUGINS}
      remarkPlugins={REMARK_PLUGINS}
      shikiTheme={CHAT_SHIKI_THEME}
      components={components}
      className="chat-markdown text-body text-ink min-w-0"
    >
      {content}
    </Streamdown>
  );
}

const markerButtonClass =
  "text-primary hover:text-primary-hover focus-visible:ring-ring/40 mx-0.5 align-super text-label rounded-sm font-medium focus-visible:ring-3";

const CITATION_MARKER_RE = /\[(\d{1,3})\]/g;

type MinimalNode = {
  type: string;
  value?: unknown;
  url?: unknown;
  identifier?: unknown;
  children?: MinimalNode[];
};

/** mdast 文本节点中的 [n] → #citation-n 链接；代码/行内代码不参与。 */
function remarkCitationLinks() {
  return (tree: unknown) => {
    walk(tree as MinimalNode);
  };
}

function walk(node: MinimalNode): void {
  const children = node.children;
  if (!children) return;
  const next: MinimalNode[] = [];
  for (const child of children) {
    if (child.type === "text" && typeof child.value === "string") {
      next.push(...splitCitationText(child.value));
      continue;
    }
    // 相邻角标 [1][2] 会被 Markdown 解析为 full reference（文本 [1] + 标签 [2]），
    // 先按原样重建再拆分；identifier 非纯数字的真实引用语法不动。
    if (
      child.type === "linkReference" &&
      typeof child.identifier === "string" &&
      /^\d{1,3}$/.test(child.identifier)
    ) {
      const markerText = collectText(child);
      if (/^\d{1,3}$/.test(markerText)) {
        next.push(...splitCitationText(`[${markerText}][${child.identifier}]`));
        continue;
      }
    }
    walk(child);
    next.push(child);
  }
  node.children = next;
}

function collectText(node: MinimalNode): string {
  if (node.children === undefined) {
    return typeof node.value === "string" ? node.value : "";
  }
  return node.children.map(collectText).join("");
}

function splitCitationText(value: string): MinimalNode[] {
  const parts: MinimalNode[] = [];
  let last = 0;
  for (const match of value.matchAll(CITATION_MARKER_RE)) {
    const start = match.index;
    if (start > last) {
      parts.push({ type: "text", value: value.slice(last, start) });
    }
    parts.push({
      type: "link",
      url: `#citation-${match[1]}`,
      children: [{ type: "text", value: match[0] }],
    });
    last = start + match[0].length;
  }
  if (last === 0) return [{ type: "text", value }];
  if (last < value.length) {
    parts.push({ type: "text", value: value.slice(last) });
  }
  return parts;
}

type RemarkPlugin = (typeof defaultRemarkPlugins)[string];

const REMARK_PLUGINS: RemarkPlugin[] = [
  ...Object.values(defaultRemarkPlugins),
  remarkCitationLinks as unknown as RemarkPlugin,
];
