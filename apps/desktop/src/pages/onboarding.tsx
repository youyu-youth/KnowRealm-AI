import { createFileRoute, redirect } from "@tanstack/react-router";
import { OnboardingWizard } from "@/features/onboarding/OnboardingWizard";
import { isOnboardingRequired } from "@/services/tauri/onboarding";

export const Route = createFileRoute("/onboarding")({
  // 已完成首启的用户直达此地址时回首页：向导永不再现，无重跑入口。
  beforeLoad: async () => {
    if (!(await isOnboardingRequired())) {
      throw redirect({ to: "/", replace: true });
    }
  },
  component: OnboardingWizard,
});
