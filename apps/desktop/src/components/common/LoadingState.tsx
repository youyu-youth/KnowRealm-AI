import { useTranslation } from "react-i18next";

export function LoadingState() {
  const { t } = useTranslation();

  return (
    <p
      role="status"
      className="max-w-workbench px-content text-body text-muted-foreground mx-auto py-8"
    >
      {t("route.loading")}
    </p>
  );
}
