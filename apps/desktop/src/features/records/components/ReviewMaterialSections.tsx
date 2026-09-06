import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "@/components/common/MarkdownContent";
import type { ReviewMaterialOut } from "@/features/records/api/types";

type OutlineNode = {
  title: string;
  children: OutlineNode[];
  items: string[];
};

function parseOutline(markdown: string): OutlineNode[] {
  const roots: OutlineNode[] = [];
  const stack: Array<{ level: number; node: OutlineNode }> = [];
  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trim();
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const node: OutlineNode = { title: heading[2], children: [], items: [] };
      while (stack.length && stack[stack.length - 1].level >= level)
        stack.pop();
      if (stack.length) stack[stack.length - 1].node.children.push(node);
      else roots.push(node);
      stack.push({ level, node });
      continue;
    }
    const item = /^(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line)?.[1];
    if (item && stack.length) stack[stack.length - 1].node.items.push(item);
    else if (item) roots.push({ title: item, children: [], items: [] });
  }
  return roots;
}

function OutlineTree({ markdown }: { markdown: string }) {
  return (
    <div className="mt-4 space-y-2">
      {parseOutline(markdown).map((node) => (
        <OutlineBranch key={node.title} node={node} />
      ))}
    </div>
  );
}

function OutlineBranch({ node }: { node: OutlineNode }) {
  return (
    <details open className="group">
      <summary className="text-body text-ink-strong focus-visible:ring-ring/40 flex cursor-pointer list-none items-center gap-2 rounded-sm py-1 font-medium focus-visible:ring-3">
        <ChevronRight
          className="text-muted-foreground size-4 shrink-0 transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        {node.title}
      </summary>
      <div className="border-border ml-2 border-l pl-5">
        {node.items.length ? (
          <ul className="text-body text-ink list-disc space-y-1 py-2 pl-4">
            {node.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        {node.children.map((child) => (
          <OutlineBranch key={child.title} node={child} />
        ))}
      </div>
    </details>
  );
}

/** 三段式预览：考前速记 → 重点清单 → 大纲树；页签阅读态与 HITL 弹窗共用。 */
export function ReviewMaterialSections({
  material,
}: {
  material: ReviewMaterialOut;
}) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0 space-y-8">
      <section>
        <h3 className="text-section font-section text-ink-strong">
          {t("record.detail.review.quickReviewTitle")}
        </h3>
        <MarkdownContent markdown={material.quick_review} />
      </section>
      <section className="border-border border-t pt-6">
        <h3 className="text-section font-section text-ink-strong">
          {t("record.detail.review.keyListTitle")}
        </h3>
        <ol className="mt-4 space-y-3">
          {material.key_list.map((item, index) => (
            <li
              key={`${index}-${item}`}
              className="text-body text-ink flex gap-3"
            >
              <span className="text-label text-muted-foreground mt-0.5 tabular-nums">
                {index + 1}.
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="border-border border-t pt-6">
        <h3 className="text-section font-section text-ink-strong">
          {t("record.detail.review.outlineTitle")}
        </h3>
        <OutlineTree markdown={material.mind_map_markdown} />
      </section>
    </div>
  );
}
