import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  LlmProviderCard,
  TencentAsrCard,
} from "@/features/settings/ProvidersSection";
import { StepHeader } from "@/features/onboarding/StepHeader";

type Props = {
  current: number;
  onNext: () => void;
};

/** 向导②供应商：直接复用设置页卡片（自带查询与保存），跳过由空态引导兜底（#38）。 */
export function ProvidersStep({ current, onNext }: Props) {
  const { t } = useTranslation();
  return (
    <div>
      <StepHeader
        current={current}
        title={t("onboarding.providers.title")}
        description={t("onboarding.providers.description")}
      />
      <div className="mt-10 flex flex-col gap-10">
        <LlmProviderCard />
        <TencentAsrCard />
      </div>
      <div className="mt-10">
        <Button variant="outline" onClick={onNext}>
          {t("onboarding.providers.skip")}
        </Button>
      </div>
    </div>
  );
}
