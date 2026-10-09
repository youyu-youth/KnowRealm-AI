import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Settings2,
  Trophy,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";

export function TodayAssets() {
  const { t } = useTranslation();
  return (
    <>
      <section
        aria-labelledby="today-assets-title"
        className="border-border-subtle border-t p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 id="today-assets-title" className="today-heading">
              {t("today.overview.assetsTitle")}
            </h2>
            <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          </div>
          <Link
            to="/library"
            className="text-label text-today-accent inline-flex items-center gap-1 hover:underline"
          >
            {t("today.overview.openLibrary")}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </div>
        <ul className="divide-border-subtle mt-2 divide-y">
          {["reviewMaterial", "knowledgePoint", "summary"].map((key) => (
            <li key={key} className="flex items-start gap-3 py-4">
              <FileText className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-body font-medium">
                  {t(`today.overview.assets.${key}.title`)}
                </p>
                <p className="text-label text-ink-muted mt-1">
                  {t(`today.overview.assets.${key}.type`)} ·{" "}
                  {t(`today.overview.assets.${key}.source`)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section
        aria-labelledby="today-chain-title"
        className="border-border-subtle border-t p-4"
      >
        <h2
          id="today-chain-title"
          className="text-body text-ink-muted font-medium"
        >
          {t("today.workspace.flow")}
        </h2>
        <div className="mt-4 grid grid-cols-4 gap-2">
          {[
            { key: "capture", Icon: FileText },
            { key: "processing", Icon: Settings2 },
            { key: "summary", Icon: CheckCircle2 },
            { key: "assets", Icon: BookOpen },
          ].map(({ key, Icon }) => (
            <div key={key} className="min-w-0 text-center">
              <Icon className="mx-auto size-6" aria-hidden="true" />
              <p className="text-label mt-2 font-medium">
                {t(`today.overview.chain.${key}`)}
              </p>
              <p className="text-label text-ink-muted mt-1 break-words">
                {t(`today.workspace.flowHints.${key}`)}
              </p>
            </div>
          ))}
        </div>
      </section>
      <section
        aria-label={t("today.rightRail.achievementTitle")}
        className="border-border-subtle flex items-start gap-3 border-t p-4"
      >
        <Trophy className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h2 className="text-body font-medium">
            {t("today.rightRail.achievementTitle")}
          </h2>
          <p className="text-label text-ink-muted mt-1">
            {t("today.overview.achievementSample")}
          </p>
        </div>
        <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
      </section>
    </>
  );
}
