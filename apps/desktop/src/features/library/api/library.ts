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
export type OrganizeScanOut = components["schemas"]["OrganizeScanOut"];
export type OrganizeProposeOut = components["schemas"]["OrganizeProposeOut"];
export type AgentProposalOut = components["schemas"]["AgentProposalOut"];
export type ProposalCreateRequest =
  components["schemas"]["ProposalCreateRequest"];
export type ProposalConfirmBody = components["schemas"]["ProposalConfirmBody"];
export type ProposalStatus = components["schemas"]["ProposalStatus"];
export type ProposalType = components["schemas"]["ProposalType"];
export type LibraryItemPatchBody = components["schemas"]["LibraryItemPatch"];

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
  getItemContent: (itemId: string, limit?: number) =>
    apiFetch<components["schemas"]["LibraryItemContentOut"]>(
      `/api/library/items/${itemId}/content${limit === undefined ? "" : `?limit=${limit}`}`,
    ),
  patchItem: (itemId: string, body: LibraryItemPatchBody) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  archiveItem: (itemId: string) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}/archive`, {
      method: "POST",
    }),
  unarchiveItem: (itemId: string) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}/unarchive`, {
      method: "POST",
    }),
  deleteItem: (itemId: string) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}`, {
      method: "DELETE",
    }),
  purgeItem: (itemId: string) =>
    apiFetch<null>(`/api/library/items/${itemId}?permanent=true`, {
      method: "DELETE",
    }),
  restoreItem: (itemId: string) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}/restore`, {
      method: "POST",
    }),
  retryItem: (itemId: string) =>
    apiFetch<LibraryItemOut>(`/api/library/items/${itemId}/retry`, {
      method: "POST",
    }),
  refetchItem: (itemId: string) =>
    apiFetch<LibraryIngestAccepted>(`/api/library/items/${itemId}/refetch`, {
      method: "POST",
    }),
  rebuildItemIndex: (itemId: string) =>
    apiFetch<{ job_id: string }>(`/api/library/items/${itemId}/rebuild-index`, {
      method: "POST",
    }),
  organizeScan: () =>
    apiFetch<OrganizeScanOut>("/api/library/organize/scan", {
      method: "POST",
    }),
  organizePropose: () =>
    apiFetch<OrganizeProposeOut>("/api/library/organize/propose", {
      method: "POST",
    }),
  listProposals: (
    params: { status?: ProposalStatus; session_id?: string } = {},
  ) => {
    const search = new URLSearchParams();
    if (params.status) search.set("status", params.status);
    if (params.session_id) search.set("session_id", params.session_id);
    const query = search.toString();
    return apiFetch<AgentProposalOut[]>(
      `/api/proposals${query ? `?${query}` : ""}`,
    );
  },
  createProposal: (body: ProposalCreateRequest) =>
    apiFetch<AgentProposalOut>("/api/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  confirmProposal: (
    proposalId: string,
    editedPayload?: ProposalConfirmBody["payload"],
  ) =>
    apiFetch<AgentProposalOut>(`/api/proposals/${proposalId}/confirm`, {
      method: "POST",
      ...(editedPayload === undefined
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              payload: editedPayload,
            } satisfies ProposalConfirmBody),
          }),
    }),
  rejectProposal: (proposalId: string) =>
    apiFetch<AgentProposalOut>(`/api/proposals/${proposalId}/reject`, {
      method: "POST",
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

/** 生命周期动作统一 mutation：成功后失效资料库缓存。 */
export function useLibraryItemAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      action,
      itemId,
    }: {
      action:
        | "archive"
        | "unarchive"
        | "delete"
        | "purge"
        | "restore"
        | "retry"
        | "refetch"
        | "rebuild-index";
      itemId: string;
    }) => {
      switch (action) {
        case "archive":
          await libraryApi.archiveItem(itemId);
          break;
        case "unarchive":
          await libraryApi.unarchiveItem(itemId);
          break;
        case "delete":
          await libraryApi.deleteItem(itemId);
          break;
        case "purge":
          await libraryApi.purgeItem(itemId);
          break;
        case "restore":
          await libraryApi.restoreItem(itemId);
          break;
        case "retry":
          await libraryApi.retryItem(itemId);
          break;
        case "refetch":
          await libraryApi.refetchItem(itemId);
          break;
        case "rebuild-index":
          await libraryApi.rebuildItemIndex(itemId);
          break;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
  });
}

export function useLibraryItemEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      body,
    }: {
      itemId: string;
      body: LibraryItemPatchBody;
    }) => libraryApi.patchItem(itemId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
  });
}
