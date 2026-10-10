import { createFileRoute } from "@tanstack/react-router";
import { TodayOverview } from "@/features/today/components/TodayOverview";

type TodaySearch = {
  view?: "orbit" | "workbench";
  course?: string;
  order?: "duration" | "date";
  panel?: "actions" | "pending" | "review";
};

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): TodaySearch => ({
    view: search.view === "orbit" ? ("orbit" as const) : ("workbench" as const),
    course: typeof search.course === "string" ? search.course : "all",
    order:
      search.order === "duration" ? ("duration" as const) : ("date" as const),
    panel:
      search.panel === "pending" || search.panel === "review"
        ? search.panel
        : ("actions" as const),
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
