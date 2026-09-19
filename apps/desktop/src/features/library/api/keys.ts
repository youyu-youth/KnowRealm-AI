export const libraryKeys = {
  all: ["library"] as const,
  items: (params: Record<string, unknown> = {}) =>
    [...libraryKeys.all, "items", params] as const,
  itemDetail: (itemId: string) =>
    [...libraryKeys.all, "itemDetail", itemId] as const,
  itemContent: (itemId: string) =>
    [...libraryKeys.all, "itemContent", itemId] as const,
  records: () => [...libraryKeys.all, "records"] as const,
  assets: () => [...libraryKeys.all, "assets"] as const,
};
