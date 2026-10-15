import { Link } from "@tanstack/react-router";
import { BookOpen, ClipboardCheck, FileText, Lightbulb } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { RecordDetailTab } from "@/features/records/components/RecordDetailPage";
import type { AssetType, RecentAsset } from "@/features/today/api/today";

const tabs: Record<AssetType, Exclude<RecordDetailTab, "summary"> | undefined> =
  {
    summary: undefined,
    knowledge_point: "knowledge-points",
    quiz: "quiz",
    review_material: "review",
  };
const icons = {
  summary: FileText,
  knowledge_point: Lightbulb,
  quiz: ClipboardCheck,
  review_material: BookOpen,
};

export function RecentAssetList({ assets }: { assets: RecentAsset[] }) {
  const { t, i18n } = useTranslation();
  return (
    <ul
      id="today-recent-assets-list"
      aria-label={t("today.recentAssets.list")}
      className="divide-border-subtle mt-2 divide-y"
    >
      {assets.map((asset) => {
        const Icon = icons[asset.asset_type];
        return (
          <li key={`${asset.record_id}:${asset.asset_type}`}>
            <Link
              to="/records/$recordId"
              params={{ recordId: asset.record_id }}
              search={{ tab: tabs[asset.asset_type] }}
              className="hover:bg-today-soft focus-visible:ring-ring flex min-w-0 items-start gap-3 py-3 focus-visible:ring-2"
            >
              <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-body font-medium break-words">
                  {asset.record_title.trim() || t("spaces.records.untitled")}
                </p>
                <p className="text-label text-ink-muted mt-1 break-words">
                  {t(`today.recentAssets.counts.${asset.asset_type}`, {
                    count: asset.asset_count,
                  })}{" "}
                  · {asset.course_name || t("today.recentAssets.unclassified")}
                </p>
                <p className="text-label text-ink-muted mt-1 break-words">
                  {t(`today.recentAssets.${asset.time_basis}`, {
                    time: new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                      year: "numeric",
                      month: "numeric",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(asset.asset_at)),
                  })}
                </p>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
