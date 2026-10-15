import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useContext, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { todayKeys } from "@/features/today/api/keys";
import { todayApi, type AssetType } from "@/features/today/api/today";
import { RecentAssetsNavigation } from "@/features/today/components/RecentAssetsNavigation";
import { RecentAssetList } from "@/features/today/components/RecentAssetList";

const assetTypes = [
  "all",
  "summary",
  "knowledge_point",
  "quiz",
  "review_material",
] as const;

export function TodayRecentAssets() {
  const { t } = useTranslation();
  const {
    asset_type: type = "all",
    assets_expanded: expanded = false,
    assets_page: page = 1,
  } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const openQuickNote = useContext(QuickNoteContext);
  const assets = useQuery({
    queryKey: todayKeys.assets(type, expanded, expanded ? page : 1),
    queryFn: () => todayApi.recentAssets(type, expanded, page),
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[2] === type &&
      previousQuery.queryKey[3] === expanded
        ? previousData
        : undefined,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const pages = Math.max(1, Math.ceil((assets.data?.total ?? 0) / 20));
  useEffect(() => {
    if (
      expanded &&
      assets.isSuccess &&
      !assets.isPlaceholderData &&
      page > pages
    ) {
      void navigate({
        search: (previous) => ({ ...previous, assets_page: pages }),
        replace: true,
        resetScroll: false,
      });
    }
  }, [
    expanded,
    assets.isSuccess,
    assets.isPlaceholderData,
    page,
    pages,
    navigate,
  ]);
  const changeType = (value: AssetType | "all") =>
    void navigate({
      search: (previous) => ({
        ...previous,
        asset_type: value,
        assets_page: 1,
      }),
      replace: true,
      resetScroll: false,
    });
  return (
    <section
      aria-labelledby="today-assets-title"
      aria-busy={assets.isFetching}
      className="min-w-0 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-assets-title" tabIndex={-1} className="today-heading">
          {t("today.recentAssets.title")}
        </h2>
        <Select
          value={type}
          items={assetTypes.map((value) => ({
            value,
            label: t(`today.recentAssets.types.${value}`),
          }))}
          onValueChange={(value) => {
            if (value != null) changeType(value);
          }}
        >
          <SelectTrigger size="sm" aria-label={t("today.recentAssets.filter")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {assetTypes.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(`today.recentAssets.types.${value}`)}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
      {assets.isPending ? (
        <p role="status" className="text-label text-ink-muted mt-3">
          {t("today.loading")}
        </p>
      ) : assets.isError ? (
        <div role="alert" className="mt-3">
          <p className="text-label">{t("today.recentAssets.error")}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => void assets.refetch()}
          >
            {t("today.retry")}
          </Button>
        </div>
      ) : assets.data.total === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>{t("today.recentAssets.empty")}</EmptyTitle>
            <EmptyDescription>
              {t("today.recentAssets.emptyHint")}
            </EmptyDescription>
          </EmptyHeader>
          <Button
            variant="outline"
            size="sm"
            disabled={!openQuickNote}
            onClick={() => openQuickNote?.()}
          >
            {t("today.workspace.newNote")}
          </Button>
        </Empty>
      ) : (
        <RecentAssetList assets={assets.data.items} />
      )}
      <RecentAssetsNavigation
        expanded={expanded}
        page={page}
        total={assets.data?.total ?? 0}
        offset={assets.isPlaceholderData ? undefined : assets.data?.offset}
        available={assets.isSuccess}
      />
      <Link
        to="/library"
        className="text-label text-today-accent mt-3 inline-flex hover:underline"
      >
        {t("today.overview.openLibrary")}
      </Link>
    </section>
  );
}
