import { RouterProvider, createRouter } from "@tanstack/react-router";
import { useState } from "react";
import { LoadingState } from "@/components/common/LoadingState";
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

export default function App() {
  const [router] = useState(createAppRouter);

  return <RouterProvider router={router} />;
}
