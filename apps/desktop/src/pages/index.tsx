import { createFileRoute } from "@tanstack/react-router";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";
import { TodayOverview } from "@/features/today/components/TodayOverview";

export const Route = createFileRoute("/")({ component: TodayPage });

export function TodayPage() {
  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col gap-6 py-7">
      <TodayOverview />
      <TodayStatsBand />
    </section>
  );
}
