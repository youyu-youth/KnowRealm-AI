import { useParams, useSearch } from "@tanstack/react-router";
import { ChatWorkspace } from "@/features/chat/ChatWorkspace";

/** 会话路由入口：解析 URL 参数并交给三栏工作区。 */
export function ChatSessionRoute() {
  const { sessionId } = useParams({ from: "/chat/$sessionId" });
  const { prompt } = useSearch({ from: "/chat/$sessionId" });
  return <ChatWorkspace sessionId={sessionId} initialPrompt={prompt} />;
}
