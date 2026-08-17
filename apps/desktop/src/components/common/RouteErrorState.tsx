import { useRouter } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export function RouteErrorState() {
  const router = useRouter();
  const { t } = useTranslation();

  return (
    <section
      role="alert"
      className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col items-start py-8"
    >
      <h1 className="text-headline font-headline text-ink-strong">
        {t("route.errorTitle")}
      </h1>
      <p className="max-w-reading text-body text-muted-foreground mt-2">
        {t("route.errorDescription")}
      </p>
      <Button
        className="hover:bg-primary-hover mt-8"
        onClick={() => void router.invalidate()}
      >
        {t("route.retry")}
      </Button>
    </section>
  );
}
