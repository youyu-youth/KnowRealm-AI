import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";
import { TodaySummaryTodos } from "@/features/today/components/TodaySummaryTodos";

export const Route = createFileRoute("/")({ component: TodayPage });

export function TodayPage() {
  const { t } = useTranslation();

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
      <header className="max-w-reading">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("today.title")}
        </h1>
        <p className="text-body text-muted-foreground mt-2">
          {t("today.description")}
        </p>
      </header>
      <TodaySummaryTodos />
      <TodayStatsBand />
    </section>
  );
}
