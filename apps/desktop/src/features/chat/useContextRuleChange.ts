import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { agentKeys } from "@/features/agent/api/authMode";

export function useContextRuleChange(sessionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["ContextRuleChange"]) =>
      contextApi.changeRules(sessionId, body),
    onSettled: () => {
      for (const resource of [
        "context",
        "context-history",
        "source",
        "sources",
      ]) {
        void client.invalidateQueries({
          queryKey: [...chatKeys.all, resource, sessionId],
        });
      }
      void client.invalidateQueries({
        queryKey: agentKeys.sessionOperations(sessionId),
      });
    },
  });
}
