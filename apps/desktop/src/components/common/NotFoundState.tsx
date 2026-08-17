import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { buttonVariants } from "@/components/ui/button";

export function NotFoundState() {
  const { t } = useTranslation();

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col items-start py-8">
      <h1 className="text-headline font-headline text-ink-strong">
        {t("route.notFoundTitle")}
      </h1>
      <p className="max-w-reading text-body text-muted-foreground mt-2">
        {t("route.notFoundDescription")}
      </p>
      <Link
        to="/"
        className={buttonVariants({ variant: "outline", className: "mt-8" })}
      >
        {t("route.backToday")}
      </Link>
    </section>
  );
}
