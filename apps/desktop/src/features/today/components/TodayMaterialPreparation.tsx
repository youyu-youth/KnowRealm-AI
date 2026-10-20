import {
  ArrowRight,
  BookOpen,
  FileText,
  Globe,
  Headphones,
  StickyNote,
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import {
  useLibraryItems,
  type LibraryItemOut,
} from "@/features/library/api/library";
import { RECENT_MATERIALS_PARAMS } from "@/features/today/api/today";
import { cn } from "@/lib/utils";

const sourceIcons = {
  AUDIO: Headphones,
  DOCUMENT: FileText,
  WEB: Globe,
  BOOK: BookOpen,
  TEXT: StickyNote,
} satisfies Record<LibraryItemOut["source_type"], typeof FileText>;

export function TodayMaterialPreparation() {
  const { t, i18n } = useTranslation();
  const materials = useLibraryItems(RECENT_MATERIALS_PARAMS, {
    refetchOnMount: "always",
    refetchIntervalMs: (data) =>
      data?.items.some((item) => item.availability === "PROCESSING") ||
      data?.backfill?.status === "PENDING" ||
      data?.backfill?.status === "RUNNING"
        ? 2000
        : false,
  });
  const dateFormat = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <section
      className="today-panel today-recent-materials p-4"
      aria-labelledby="today-material-preparation-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-material-preparation-title" className="today-heading">
          {t("today.redesign.preparation")}
        </h2>
        <Link
          to="/library"
          className="text-label text-ink-muted inline-flex items-center gap-1 hover:underline"
        >
          {t("today.redesign.openLibrary")}
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
      {materials.isPending ? (
        <p role="status" className="text-label text-ink-muted mt-3 py-4">
          {t("library.loading")}
        </p>
      ) : materials.isError ? (
        <div role="alert" className="mt-3">
          <p className="text-label text-destructive">
            {t("today.recentMaterials.error")}
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void materials.refetch()}
          >
            {t("today.retry")}
          </Button>
        </div>
      ) : materials.data.items.length === 0 ? (
        <p role="status" className="text-label text-ink-muted mt-3 py-4">
          {t("today.recentMaterials.empty")}
        </p>
      ) : (
        <ul
          className="mt-3 grid gap-1"
          aria-label={t("today.recentMaterials.list")}
        >
          {materials.data.items.map((material) => {
            const Icon = sourceIcons[material.source_type];
            return (
              <li key={material.id} className="min-w-0">
                <Link
                  to="/library"
                  search={{
                    domain: "sources",
                    selType: "item",
                    sel: material.id,
                  }}
                  className={cn(
                    buttonVariants({ variant: "ghost" }),
                    "today-material-entry h-auto w-full items-start justify-start gap-3 px-1 py-2 text-left whitespace-normal",
                  )}
                >
                  <Icon className="mt-1 size-5 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span
                      className="text-body line-clamp-2 break-words"
                      title={material.title}
                    >
                      {material.title}
                    </span>
                    <span className="text-label text-ink-muted mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span>
                        {t(`library.sourceTypes.${material.source_type}`)}
                      </span>
                      <time
                        dateTime={material.created_at}
                        title={new Date(material.created_at).toLocaleString(
                          i18n.resolvedLanguage,
                        )}
                      >
                        {dateFormat.format(new Date(material.created_at))}
                      </time>
                      {material.availability === "PROCESSING" ||
                      material.availability === "FAILED" ? (
                        <StatusTag
                          tone={
                            material.availability === "FAILED"
                              ? "danger"
                              : "warning"
                          }
                        >
                          {t(`library.availability.${material.availability}`)}
                        </StatusTag>
                      ) : null}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
