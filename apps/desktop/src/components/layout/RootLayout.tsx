import { Outlet, useLocation } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";

export function RootLayout() {
  const pathname = useLocation({ select: (location) => location.pathname });
  // 首启向导在 AppShell 之外全屏呈现：无侧栏与捕获入口，向导期间也因此
  // 结构性不写 last_route（13 号豁免扩展为"设置页与首启向导除外"）。
  if (pathname.startsWith("/onboarding")) return <Outlet />;
  return <AppShell />;
}
