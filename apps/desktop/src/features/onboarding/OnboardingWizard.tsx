import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BookOpenText, CircleCheck } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { DirectoryStep } from "@/features/onboarding/DirectoryStep";
import { LanguageStep } from "@/features/onboarding/LanguageStep";
import { ProfileStep } from "@/features/onboarding/ProfileStep";
import { ProvidersStep } from "@/features/onboarding/ProvidersStep";
import { isUiLanguage } from "@/i18n/language";
import { settingsApi } from "@/features/settings/api/settings";
import { completeOnboarding } from "@/services/tauri/onboarding";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** 首启四步向导：语言 → 目录 → 供应商 → 角色 → 完成。四步全可跳过，
 * 完成时把当前界面语言写入偏好（跳过=接受预选）并写 onboarded（经壳）。 */
export function OnboardingWizard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState(0);
  const [entering, setEntering] = useState(false);
  const [enterError, setEnterError] = useState<string | null>(null);

  const enterApp = async () => {
    setEntering(true);
    setEnterError(null);
    try {
      // 当前选中项落偏好：失败与完成失败同样阻断并提示，否则下次启动会被偏好校正回旧值。
      const language = i18n.language;
      await settingsApi.updatePreferences({
        language: isUiLanguage(language) ? language : "zh",
      });
      await completeOnboarding();
      await navigate({ to: "/" });
    } catch (error) {
      setEnterError(errorMessage(error));
      setEntering(false);
    }
  };

  return (
    <div className="bg-canvas text-foreground min-h-screen">
      <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-8 pt-12 pb-14">
        <header className="flex items-center gap-3">
          <BookOpenText
            className="text-ink-strong size-5 shrink-0"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-body text-ink-strong font-section">
              {t("app.name")}
            </p>
            <p className="text-label text-muted-foreground">
              {t("app.tagline")}
            </p>
          </div>
        </header>
        <div className="mt-14 flex flex-1 flex-col">
          {stepIndex === 0 ? (
            <LanguageStep current={1} onNext={() => setStepIndex(1)} />
          ) : null}
          {stepIndex === 1 ? (
            <DirectoryStep current={2} onNext={() => setStepIndex(2)} />
          ) : null}
          {stepIndex === 2 ? (
            <ProvidersStep current={3} onNext={() => setStepIndex(3)} />
          ) : null}
          {stepIndex === 3 ? (
            <ProfileStep current={4} onNext={() => setStepIndex(4)} />
          ) : null}
          {stepIndex === 4 ? (
            <section>
              <CircleCheck
                className="text-success-foreground size-7"
                aria-hidden="true"
              />
              <h1 className="text-headline font-headline text-ink-strong mt-4">
                {t("onboarding.done.title")}
              </h1>
              <p className="text-body text-muted-foreground max-w-reading mt-3">
                {t("onboarding.done.description")}
              </p>
              {enterError ? (
                <Alert variant="destructive" className="mt-8 w-auto">
                  <AlertDescription>{enterError}</AlertDescription>
                </Alert>
              ) : null}
              <div className="mt-8">
                <Button disabled={entering} onClick={() => void enterApp()}>
                  {entering ? (
                    <Spinner
                      data-icon="inline-start"
                      aria-label={t("onboarding.done.entering")}
                    />
                  ) : null}
                  {t("onboarding.done.enter")}
                </Button>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
