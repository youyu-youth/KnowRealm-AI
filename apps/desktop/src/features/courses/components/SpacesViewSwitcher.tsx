import { LayoutGrid, List, Rows3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { SpacesSearch } from "@/features/courses/spacesSearch";

export function SpacesViewSwitcher({
  search,
  onChange,
}: {
  search: SpacesSearch;
  onChange: (next: SpacesSearch) => void;
}) {
  const { t } = useTranslation();
  const view = search.view ?? "tracks";
  return (
    <div
      role="group"
      aria-label={t("spaces.grid.viewLabel")}
      className="border-border bg-background flex items-center gap-0.5 rounded-lg border p-0.5"
    >
      {(
        [
          { value: "tracks", icon: Rows3, label: "viewTracks" },
          { value: "list", icon: List, label: "viewList" },
          { value: "grid", icon: LayoutGrid, label: "viewGrid" },
        ] as const
      ).map(({ value, icon: Icon, label }) => (
        <Button
          key={value}
          size="sm"
          variant="ghost"
          aria-pressed={view === value}
          aria-label={t(`spaces.grid.${label}`)}
          className={view === value ? "bg-spaces-soft text-spaces-accent" : ""}
          onClick={() => onChange({ ...search, view: value })}
        >
          <Icon aria-hidden="true" />
          {t(`spaces.grid.${label}Short`)}
        </Button>
      ))}
    </div>
  );
}
