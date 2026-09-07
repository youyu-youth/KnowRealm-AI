export const searchKeys = {
  results: (q: string, limit?: number) =>
    ["search", "results", q, limit ?? null] as const,
};
