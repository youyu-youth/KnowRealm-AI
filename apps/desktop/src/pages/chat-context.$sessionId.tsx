import { createFileRoute } from "@tanstack/react-router";
import { ChatContextPage } from "@/features/chat/ChatContextPage";

export const Route = createFileRoute("/chat-context/$sessionId")({
  component: function ContextRoute() {
    const { sessionId } = Route.useParams();
    return <ChatContextPage key={sessionId} sessionId={sessionId} />;
  },
});
