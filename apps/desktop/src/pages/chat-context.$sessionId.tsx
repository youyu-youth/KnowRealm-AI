import { createFileRoute } from "@tanstack/react-router";
import { ChatContextPage } from "@/features/chat/ChatContextPage";

export const Route = createFileRoute("/chat-context/$sessionId")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { view?: "actual" | "next" } => ({
    view: search.view === "next" ? "next" : undefined,
  }),
  component: function ContextRoute() {
    const { sessionId } = Route.useParams();
    return <ChatContextPage key={sessionId} sessionId={sessionId} />;
  },
});
