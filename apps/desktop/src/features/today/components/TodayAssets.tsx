import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  ChevronDown,
  BookOpen,
  CheckCircle2,
  FileText,
  Settings2,
  Trophy,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { TodayRecentAssets } from "@/features/today/components/TodayRecentAssets";

export function TodayAssets() {
  const { t } = useTranslation();
  return (
    <>
      <TodayRecentAssets />
      <Collapsible className="today-supporting-assets">
        <CollapsibleTrigger className="text-label text-ink-muted flex w-full items-center justify-between px-4 py-3">
          {t("today.redesign.moreInsights")}
          <ChevronDown className="size-4" aria-hidden="true" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <section aria-labelledby="today-chain-title" className="p-4">
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
            className="flex items-start gap-3 p-4"
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
        </CollapsibleContent>
      </Collapsible>
    </>
  );
}
