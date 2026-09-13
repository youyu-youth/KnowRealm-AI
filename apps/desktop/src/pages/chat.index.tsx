import { createFileRoute } from "@tanstack/react-router";
import { ChatWorkspace } from "@/features/chat/ChatWorkspace";

export const Route = createFileRoute("/chat/")({
  component: ChatWorkspace,
});
