import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { contextApi } from "@/features/chat/api/context";
import { chatKeys } from "@/features/chat/api/keys";
import { agentKeys } from "@/features/agent/api/authMode";

export function useContextPinChange(sessionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["ContextPinChange"]) =>
      contextApi.changePin(sessionId, body),
    onSettled: () => {
      void client.invalidateQueries({
        queryKey: [...chatKeys.all, "context", sessionId],
      });
      void client.invalidateQueries({
        queryKey: agentKeys.sessionOperations(sessionId),
      });
    },
  });
}
