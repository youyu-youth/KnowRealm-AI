import { createFileRoute } from "@tanstack/react-router";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";
import { TodaySummaryTodos } from "@/features/today/components/TodaySummaryTodos";

export const Route = createFileRoute("/")({ component: TodayPage });

export function TodayPage() {
  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-6">
      <TodaySummaryTodos />
      <TodayStatsBand />
    </section>
  );
}
