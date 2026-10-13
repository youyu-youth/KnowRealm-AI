import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { useState } from "react";
import { createQueryClient } from "@/app/queryClient";
import { LoadingState } from "@/components/common/LoadingState";
import { WindowTitleBar } from "@/components/layout/WindowTitleBar";
import { TitleBarSearchHostContext } from "@/components/layout/titleBarSearchHostContext";
import "@/i18n";
import { routeTree } from "@/routeTree.gen";

function createAppRouter() {
  return createRouter({
    routeTree,
    defaultPreload: "intent",
    defaultPendingComponent: LoadingState,
    scrollRestoration: true,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}

export default function App({
  queryClient: initialQueryClient,
}: { queryClient?: QueryClient } = {}) {
  const [router] = useState(createAppRouter);
  const [searchHost, setSearchHost] = useState<HTMLDivElement | null>(null);
  const [queryClient] = useState(
    () => initialQueryClient ?? createQueryClient(),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <div className="bg-canvas flex h-screen min-w-0 flex-col overflow-hidden">
        <TitleBarSearchHostContext value={searchHost}>
          <WindowTitleBar searchHostRef={setSearchHost} />
          <div className="min-h-0 flex-1 overflow-y-auto">
            <RouterProvider router={router} />
          </div>
        </TitleBarSearchHostContext>
      </div>
    </QueryClientProvider>
  );
}
