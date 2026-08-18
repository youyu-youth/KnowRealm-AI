import { useTranslation } from "react-i18next";

// 稳定宿主：学习记录将在后续计划接入，明确标示未接入，不渲染任何记录或模拟空列表。
export function CourseRecordsPanel() {
  const { t } = useTranslation();

  return (
    <div className="border-border mt-2 border-t pt-8">
      <div className="flex items-center gap-3">
        <h2 className="text-section font-section text-ink">
          {t("spaces.records.pendingTitle")}
        </h2>
        <span className="bg-surface-subtle text-label text-muted-foreground rounded-xs px-1.5 py-0.5">
          {t("nav.unavailable")}
        </span>
      </div>
      <p className="max-w-reading text-body text-muted-foreground mt-3">
        {t("spaces.records.pendingDescription")}
      </p>
    </div>
  );
}
