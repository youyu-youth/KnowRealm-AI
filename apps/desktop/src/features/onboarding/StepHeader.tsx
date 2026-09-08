import { useTranslation } from "react-i18next";

const TOTAL_STEPS = 4;

type Props = {
  current: number;
  title: string;
  description: string;
};

export function StepHeader({ current, title, description }: Props) {
  const { t } = useTranslation();
  return (
    <header>
      <p className="text-label text-muted-foreground">
        {t("onboarding.stepOf", { current, total: TOTAL_STEPS })}
      </p>
      <h1 className="text-headline font-headline text-ink-strong mt-2">
        {title}
      </h1>
      <p className="text-body text-muted-foreground max-w-reading mt-3">
        {description}
      </p>
    </header>
  );
}
