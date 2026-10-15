import { createFileRoute } from "@tanstack/react-router";
import { TodayOverview } from "@/features/today/components/TodayOverview";
import type { AssetType } from "@/features/today/api/today";

type TodaySearch = {
  asset_type?: AssetType | "all";
  assets_expanded?: boolean;
  assets_page?: number;
  view?: "orbit" | "workbench";
  course?: string;
  order?: "duration" | "date";
  action_status?: "pending" | "done";
  completed_page?: number;
  panel?: "actions" | "pending" | "review";
  inspector?: "summary" | "focus";
  record?: string;
  task?: string;
};

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): TodaySearch => ({
    asset_type:
      search.asset_type === "summary" ||
      search.asset_type === "knowledge_point" ||
      search.asset_type === "quiz" ||
      search.asset_type === "review_material"
        ? search.asset_type
        : "all",
    assets_expanded:
      search.assets_expanded === true || search.assets_expanded === "true",
    assets_page:
      Number.isSafeInteger(Number(search.assets_page)) &&
      Number(search.assets_page) > 0 &&
      Number(search.assets_page) <= Math.floor(Number.MAX_SAFE_INTEGER / 20)
        ? Number(search.assets_page)
        : 1,
    view: search.view === "orbit" ? ("orbit" as const) : ("workbench" as const),
    course: typeof search.course === "string" ? search.course : "all",
    action_status: search.action_status === "done" ? "done" : "pending",
    completed_page:
      Number.isSafeInteger(Number(search.completed_page)) &&
      Number(search.completed_page) > 0
        ? Number(search.completed_page)
        : 1,
    order:
      search.order === "duration" ? ("duration" as const) : ("date" as const),
    panel:
      search.panel === "pending" || search.panel === "review"
        ? search.panel
        : ("actions" as const),
    record: typeof search.record === "string" ? search.record : undefined,
    task: typeof search.task === "string" ? search.task : undefined,
    inspector:
      search.inspector === "summary" || search.inspector === "focus"
        ? search.inspector
        : undefined,
  }),
  component: TodayPage,
});

export function TodayPage() {
  return (
    <section className="today-page work-surface-enter min-h-full p-2">
      <TodayOverview />
    </section>
  );
}
