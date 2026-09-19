import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";
import { libraryKeys } from "@/features/library/api/keys";
import type {
  LibraryAvailabilityFilter,
  LibrarySourceTypeFilter,
  LibraryView,
} from "@/features/library/librarySearch";

export type LibraryItemOut = components["schemas"]["LibraryItemOut"];
export type LibraryItemDetailOut =
  components["schemas"]["LibraryItemDetailOut"];
export type LibraryItemListOut = components["schemas"]["LibraryItemListOut"];
export type LibraryRecordOut = components["schemas"]["LibraryRecordOut"];
export type LibraryAssetOut = components["schemas"]["LibraryAssetOut"];
export type BackfillStatusOut = components["schemas"]["BackfillStatusOut"];
export type LibraryIngestRequest =
  components["schemas"]["LibraryIngestRequest"];
export type LibraryIngestAccepted =
  components["schemas"]["LibraryIngestAccepted"];

export type LibraryItemsParams = {
  view?: LibraryView;
  sourceType?: LibrarySourceTypeFilter;
  availability?: LibraryAvailabilityFilter;
  courseId?: string;
  unclassified?: boolean;
  q?: string;
  offset?: number;
  limit?: number;
};

export const libraryApi = {
  listItems: (params: LibraryItemsParams = {}) => {
    const search = new URLSearchParams();
    if (params.view && params.view !== "all") search.set("view", params.view);
    if (params.sourceType) search.set("source_type", params.sourceType);
    if (params.availability) search.set("availability", params.availability);
    if (params.courseId) search.set("course_id", params.courseId);
    if (params.unclassified) search.set("unclassified", "true");
    if (params.q) search.set("q", params.q);
    if (params.offset) search.set("offset", String(params.offset));
    if (params.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return apiFetch<LibraryItemListOut>(
      `/api/library/items${query ? `?${query}` : ""}`,
    );
  },
  getItem: (itemId: string) =>
    apiFetch<LibraryItemDetailOut>(`/api/library/items/${itemId}`),
  getItemContent: (itemId: string) =>
    apiFetch<components["schemas"]["LibraryItemContentOut"]>(
      `/api/library/items/${itemId}/content`,
    ),
  patchItem: (itemId: string, body: { favorite?: boolean }) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  ingest: (body: LibraryIngestRequest) =>
    apiFetch<LibraryIngestAccepted>("/api/library/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  ingestFile: (
    file: File,
    options: { courseId?: string; allowDuplicate?: boolean } = {},
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (options.courseId) form.append("course_id", options.courseId);
    if (options.allowDuplicate) form.append("allow_duplicate", "true");
    return apiFetch<LibraryIngestAccepted>("/api/library/ingest/file", {
      method: "POST",
      body: form,
    });
  },
  listRecords: () => apiFetch<LibraryRecordOut[]>("/api/library/records"),
  listAssets: () => apiFetch<LibraryAssetOut[]>("/api/library/assets"),
};

export function useLibraryItems(
  params: LibraryItemsParams = {},
  options?: {
    /** 基于最新数据的轮询间隔：PROCESSING 条目存在时返回间隔，终态返回 false。 */
    refetchIntervalMs?: (
      data: LibraryItemListOut | undefined,
    ) => number | false;
  },
) {
  return useQuery({
    queryKey: libraryKeys.items(params),
    queryFn: () => libraryApi.listItems(params),
    placeholderData: keepPreviousData,
    refetchInterval: options?.refetchIntervalMs
      ? (query) => options.refetchIntervalMs?.(query.state.data)
      : false,
  });
}

export function useLibraryItemDetail(itemId: string | null) {
  return useQuery({
    queryKey: libraryKeys.itemDetail(itemId ?? ""),
    // enabled 保证 queryFn 仅在 itemId 非空时执行，as string 仅做类型收窄
    queryFn: () => libraryApi.getItem(itemId as string),
    enabled: itemId !== null,
  });
}

export function useLibraryItemContent(itemId: string | null) {
  return useQuery({
    queryKey: libraryKeys.itemContent(itemId ?? ""),
    // enabled 保证 queryFn 仅在 itemId 非空时执行，as string 仅做类型收窄
    queryFn: () => libraryApi.getItemContent(itemId as string),
    enabled: itemId !== null,
    staleTime: 60_000,
  });
}

export function useLibraryRecords() {
  return useQuery({
    queryKey: libraryKeys.records(),
    queryFn: libraryApi.listRecords,
  });
}

export function useLibraryAssets() {
  return useQuery({
    queryKey: libraryKeys.assets(),
    queryFn: libraryApi.listAssets,
  });
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, favorite }: { itemId: string; favorite: boolean }) =>
      libraryApi.patchItem(itemId, { favorite }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
  });
}
