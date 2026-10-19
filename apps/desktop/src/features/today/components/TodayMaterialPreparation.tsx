import { ArrowRight, FileText } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import { materialExamples } from "@/features/today/materialExamples";

export function TodayMaterialPreparation({
  selected,
  onSelect,
}: {
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <section
      className="today-panel today-recent-materials p-4"
      aria-labelledby="today-material-preparation-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-material-preparation-title" className="today-heading">
          {t("today.redesign.preparation")}
        </h2>
        <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
        <Link
          to="/library"
          className="text-label text-ink-muted inline-flex items-center gap-1 hover:underline"
        >
          {t("today.redesign.openLibrary")}
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
      <ul className="mt-3 grid gap-1">
        {materialExamples.slice(0, 3).map((material, index) => (
          <li key={material.key}>
            <Button
              variant="ghost"
              className="today-material-entry h-auto w-full justify-start gap-3 px-1 py-2 text-left whitespace-normal"
              aria-pressed={selected === index}
              onClick={() => onSelect(index)}
            >
              <FileText className="size-5 shrink-0" aria-hidden="true" />
              <span className="min-w-0">
                <span className="text-body block break-words">
                  {t(`today.redesign.examples.${material.key}.shortTitle`)}
                </span>
                <span className="text-label text-ink-muted mt-1 block">
                  {material.filename}
                </span>
              </span>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
