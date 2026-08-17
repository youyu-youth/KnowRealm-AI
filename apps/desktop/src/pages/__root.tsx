import { createRootRoute } from "@tanstack/react-router";
import { NotFoundState } from "@/components/common/NotFoundState";
import { RouteErrorState } from "@/components/common/RouteErrorState";
import { AppShell } from "@/components/layout/AppShell";

export const Route = createRootRoute({
  component: AppShell,
  errorComponent: RouteErrorState,
  notFoundComponent: NotFoundState,
});
