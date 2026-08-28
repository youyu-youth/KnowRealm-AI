import { createFileRoute } from "@tanstack/react-router";
import { ChatSessionPage } from "@/features/chat/ChatSessionPage";

export const Route = createFileRoute("/chat/$sessionId")({
  component: ChatSessionPage,
});
