import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";

/** “未配置 AI 服务”的统一引导卡：不再就地配置，一律跳设置页完成（plan 14 工单 02）。 */
export function ProviderSetupGuide() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="border-border bg-surface-subtle/40 rounded-card max-w-reading border p-6">
      <div className="flex items-center gap-3">
        <Settings aria-hidden="true" className="text-muted-foreground size-5" />
        <h2 className="text-section font-section text-ink">
          {t("providerGuide.title")}
        </h2>
      </div>
      <p className="text-body text-muted-foreground mt-2">
        {t("providerGuide.description")}
      </p>
      <Button
        className="mt-5"
        onClick={() => void navigate({ to: "/settings" })}
      >
        {t("providerGuide.action")}
      </Button>
    </div>
  );
}
