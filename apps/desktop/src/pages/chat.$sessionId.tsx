import { createFileRoute } from "@tanstack/react-router";
import { ChatSessionPage } from "@/features/chat/ChatSessionPage";

export const Route = createFileRoute("/chat/$sessionId")({
  validateSearch: (search: Record<string, unknown>): { prompt?: string } => ({
    prompt:
      typeof search.prompt === "string" && search.prompt.length <= 8_000
        ? search.prompt
        : undefined,
  }),
  component: ChatSessionPage,
});
