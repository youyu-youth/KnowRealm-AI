import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export function RecentAssetsNavigation({
  expanded,
  page,
  total,
  offset,
  available,
}: {
  expanded: boolean;
  page: number;
  total: number;
  offset: number | undefined;
  available: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate({ from: "/" });
  const pages = Math.max(1, Math.ceil(total / 20));
  const previousButton = useRef<HTMLButtonElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const focusDirection = useRef<"previous" | "next" | null>(null);
  useEffect(() => {
    if (focusDirection.current == null || offset !== (page - 1) * 20) return;
    const target =
      focusDirection.current === "next"
        ? nextButton.current
        : previousButton.current;
    if (target && !target.disabled) target.focus();
    else document.getElementById("today-assets-title")?.focus();
    focusDirection.current = null;
  }, [offset, page, pages]);
  const changePage = (next: number) => {
    focusDirection.current = next > page ? "next" : "previous";
    void navigate({
      search: (previous) => ({ ...previous, assets_page: next }),
      replace: true,
      resetScroll: false,
    });
  };
  if (!expanded && total <= 5) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={expanded}
        onClick={() =>
          void navigate({
            search: (previous) => ({
              ...previous,
              assets_expanded: !expanded,
              assets_page: 1,
            }),
            replace: true,
            resetScroll: false,
          })
        }
      >
        {t(
          expanded
            ? "today.recentAssets.collapse"
            : "today.recentAssets.showAll",
        )}
      </Button>
      {expanded && available && pages > 1 && (
        <nav
          aria-label={t("today.recentAssets.pagination")}
          className="flex flex-wrap items-center gap-2"
        >
          <Button
            ref={previousButton}
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => changePage(page - 1)}
          >
            {t("today.progress.previous")}
          </Button>
          <span className="text-label text-ink-muted tabular-nums">
            {t("today.progress.page", { page, pages })}
          </span>
          <Button
            ref={nextButton}
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => changePage(page + 1)}
          >
            {t("today.progress.next")}
          </Button>
        </nav>
      )}
    </div>
  );
}
