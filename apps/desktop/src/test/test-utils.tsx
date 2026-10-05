import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import "@/i18n";

export function renderWithQuery(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const rendered = render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
  // queryClient 供测试驱动缓存翻转（setQueryData / invalidate）。
  return { ...rendered, queryClient };
}
