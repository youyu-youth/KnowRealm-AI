import { useQuery } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { chatKeys } from "@/features/chat/api/keys";
import { apiFetch } from "@/services/http/client";

export type AgentId = components["schemas"]["AgentId"];

export function useAgents() {
  return useQuery({
    queryKey: chatKeys.agents(),
    queryFn: () => apiFetch<components["schemas"]["AgentOut"][]>("/api/agents"),
  });
}
