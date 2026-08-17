import { createFileRoute } from "@tanstack/react-router";
import { BookOpenText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

export const Route = createFileRoute("/spaces")({ component: SpacesPage });

export function SpacesPage() {
  const { t } = useTranslation();

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
      <header className="flex items-start justify-between gap-8">
        <div className="max-w-reading">
          <h1 className="text-headline font-headline text-ink-strong">
            {t("spaces.title")}
          </h1>
          <p className="text-body text-muted-foreground mt-2">
            {t("spaces.description")}
          </p>
        </div>
        <Button
          disabled
          className="hover:bg-primary-hover disabled:hover:bg-primary shrink-0 disabled:pointer-events-auto disabled:opacity-70"
        >
          {t("spaces.create")}
        </Button>
      </header>
      <Empty className="mt-12 flex-1 items-start justify-start gap-6 rounded-none border-x-0 border-t border-b-0 border-solid bg-transparent px-0 py-8 text-left">
        <EmptyHeader className="max-w-reading items-start text-left">
          <EmptyMedia className="text-muted-foreground">
            <BookOpenText className="size-5" aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle className="text-section font-section text-ink">
            {t("spaces.emptyTitle")}
          </EmptyTitle>
          <EmptyDescription className="max-w-reading text-body text-left">
            {t("spaces.emptyDescription")}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    </section>
  );
}
