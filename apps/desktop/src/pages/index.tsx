import { createFileRoute } from "@tanstack/react-router";
import { TodayOverview } from "@/features/today/components/TodayOverview";

type TodaySearch = {
  view?: "orbit" | "workbench";
  course?: string;
  order?: "duration" | "date";
  action_status?: "pending" | "done";
  completed_page?: number;
  pending_filter?: "all" | "summary" | "processing";
  pending_page?: number;
  panel?: "actions" | "pending" | "review";
  inspector?: "focus";
  task?: string;
};

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): TodaySearch => ({
    view: search.view === "orbit" ? ("orbit" as const) : ("workbench" as const),
    course: typeof search.course === "string" ? search.course : "all",
    action_status: search.action_status === "done" ? "done" : "pending",
    pending_filter:
      search.pending_filter === "summary" ||
      search.pending_filter === "processing"
        ? search.pending_filter
        : "all",
    pending_page:
      Number.isSafeInteger(Number(search.pending_page)) &&
      Number(search.pending_page) > 0
        ? Number(search.pending_page)
        : 1,
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
    task: typeof search.task === "string" ? search.task : undefined,
    inspector: search.inspector === "focus" ? search.inspector : undefined,
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
