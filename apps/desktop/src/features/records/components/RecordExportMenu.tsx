import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Download, FileText } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordDetailTab } from "@/features/records/components/RecordDetailPage";
import { selectActiveKnowledgePoints } from "@/features/records/export/serializers";
import type {
  ExportableAsset,
  RecordExportState,
} from "@/features/records/export/useRecordExport";

type RecordExportMenuProps = {
  recordId: string;
  tab: RecordDetailTab;
  busy: boolean;
  onExport: (asset: ExportableAsset) => void;
};

type CurrentTabAvailability = {
  asset: ExportableAsset | null;
  disabledReason: string | null;
};

/**
 * Record 标题区的统一导出菜单。单项导出只对当前受支持且有正式内容的资产可用；
 * 禁用原因直接呈现在菜单项内，键盘操作由菜单原语提供。
 */
export function RecordExportMenu({
  recordId,
  tab,
  busy,
  onExport,
}: RecordExportMenuProps) {
  const { t } = useTranslation();
  const summary = useQuery({
    queryKey: recordKeys.summary(recordId),
    queryFn: () => recordApi.getSummary(recordId),
    enabled: tab === "summary",
  });
  const knowledgePoints = useQuery({
    queryKey: recordKeys.knowledgePoints(recordId),
    queryFn: () => recordApi.getKnowledgePoints(recordId),
    enabled: tab === "knowledge-points",
  });

  const currentTab = useMemo<CurrentTabAvailability>(() => {
    if (tab === "summary") {
      if (summary.isPending || summary.isError) {
        return {
          asset: "summary",
          disabledReason: t("record.detail.export.contentUnavailable"),
        };
      }
      const content = summary.data?.summary;
      if (!content) {
        return {
          asset: "summary",
          disabledReason: t("record.detail.export.summaryMissing"),
        };
      }
      if (content.status !== "CONFIRMED") {
        return {
          asset: "summary",
          disabledReason: t("record.detail.export.summaryNotConfirmed"),
        };
      }
      return { asset: "summary", disabledReason: null };
    }
    if (tab === "knowledge-points") {
      if (knowledgePoints.isPending || knowledgePoints.isError) {
        return {
          asset: "knowledge-points",
          disabledReason: t("record.detail.export.contentUnavailable"),
        };
      }
      const hasActive =
        selectActiveKnowledgePoints(knowledgePoints.data?.items ?? []).length >
        0;
      return {
        asset: "knowledge-points",
        disabledReason: hasActive
          ? null
          : t("record.detail.export.knowledgePointsEmpty"),
      };
    }
    return {
      asset: null,
      disabledReason: t("record.detail.export.unsupportedTab"),
    };
  }, [knowledgePoints, summary, t, tab]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" size="sm" disabled={busy} />}
      >
        <Download aria-hidden="true" />
        {t("record.detail.export.menuLabel")}
        <ChevronDown aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuItem
          disabled={
            busy ||
            currentTab.asset === null ||
            currentTab.disabledReason !== null
          }
          onClick={() => {
            if (currentTab.asset) onExport(currentTab.asset);
          }}
        >
          <FileText aria-hidden="true" />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm">
              {t("record.detail.export.currentTab")}
            </span>
            {currentTab.disabledReason ? (
              <span className="text-muted-foreground text-xs">
                {currentTab.disabledReason}
              </span>
            ) : null}
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type RecordExportStatusProps = {
  state: RecordExportState;
  onOpenFile: (path: string) => void;
};

/** 导出结果的页内反馈：进行中、暂无内容、失败与保存成功（含按需打开）。 */
export function RecordExportStatus({
  state,
  onOpenFile,
}: RecordExportStatusProps) {
  const { t } = useTranslation();
  if (state.phase === "idle" || state.phase === "exporting") {
    if (state.phase === "idle") return null;
    return (
      <p role="status" className="text-label text-muted-foreground mt-3">
        {t("record.detail.export.exporting")}
      </p>
    );
  }
  if (state.phase === "unavailable") {
    return (
      <p role="status" className="text-label text-muted-foreground mt-3">
        {state.message}
      </p>
    );
  }
  if (state.phase === "failed") {
    return (
      <p role="alert" className="text-body text-destructive mt-3">
        {state.message}
      </p>
    );
  }
  return (
    <div className="mt-3 flex min-w-0 flex-wrap items-center gap-3">
      <p role="status" className="text-label text-ink min-w-0 break-all">
        {t("record.detail.export.savedTo")}：{state.path}
      </p>
      <Button
        variant="outline"
        size="sm"
        onClick={() => onOpenFile(state.path)}
      >
        {t("record.detail.export.openFile")}
      </Button>
      {state.openError ? (
        <p role="alert" className="text-label text-destructive w-full">
          {t("record.detail.export.openFailed")}：{state.openError}
        </p>
      ) : null}
    </div>
  );
}
