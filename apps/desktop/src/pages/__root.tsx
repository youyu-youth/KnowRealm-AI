import { createRootRoute, redirect } from "@tanstack/react-router";
import { NotFoundState } from "@/components/common/NotFoundState";
import { RootLayout } from "@/components/layout/RootLayout";
import { RouteErrorState } from "@/components/common/RouteErrorState";
import { isOnboardingRequired } from "@/services/tauri/onboarding";

export const Route = createRootRoute({
  // 首启分流先于一切路由渲染：未完成向导时任何地址都进 /onboarding，
  // 托盘"显示"与全局快捷键因此没有绕过向导的入口。
  beforeLoad: async ({ location }) => {
    if ((await isOnboardingRequired()) && location.pathname !== "/onboarding") {
      throw redirect({ to: "/onboarding", replace: true });
    }
  },
  component: RootLayout,
  errorComponent: RouteErrorState,
  notFoundComponent: NotFoundState,
});
