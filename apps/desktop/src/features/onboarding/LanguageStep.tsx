import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { applyLanguage } from "@/i18n";
import { isUiLanguage, UI_LANGUAGES } from "@/i18n/language";
import { StepHeader } from "@/features/onboarding/StepHeader";

type Props = {
  current: number;
  onNext: () => void;
};

/** 向导①界面语言：预选首帧语言（本地缓存 ?? 系统语言），切换即时生效；
 * 「继续」即接受当前选中项，完成向导时由向导统一写入偏好（跳过=接受预选）。 */
export function LanguageStep({ current, onNext }: Props) {
  const { t, i18n } = useTranslation();
  const [language, setLanguage] = useState(() =>
    isUiLanguage(i18n.language) ? i18n.language : "zh",
  );

  const select = (value: string) => {
    if (!isUiLanguage(value)) return;
    setLanguage(value);
    void applyLanguage(value);
  };

  return (
    <div>
      <StepHeader
        current={current}
        title={t("onboarding.language.title")}
        description={t("onboarding.language.description")}
      />
      <Field className="mt-10">
        <RadioGroup value={language} onValueChange={select} className="gap-3">
          {UI_LANGUAGES.map((item) => {
            const id = `onboarding-language-${item}`;
            return (
              <Field key={id} orientation="horizontal">
                <RadioGroupItem id={id} value={item} />
                <FieldLabel htmlFor={id}>
                  {t(`settings.preferences.language.${item}`)}
                </FieldLabel>
              </Field>
            );
          })}
        </RadioGroup>
      </Field>
      <div className="mt-10">
        <Button onClick={onNext}>{t("onboarding.language.confirm")}</Button>
      </div>
    </div>
  );
}
