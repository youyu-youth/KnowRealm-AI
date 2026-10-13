import { createFileRoute } from "@tanstack/react-router";
import { ChatContextPage } from "@/features/chat/ChatContextPage";

export const Route = createFileRoute("/chat-context/$sessionId")({
  validateSearch: (
    search: Record<string, unknown>,
  ): {
    view?: "actual" | "next" | "sources";
    source?: string;
    pin?: string;
    pinVersion?: number;
    q?: string;
    cursor?: string;
    searchCursor?: string;
    version?: string;
    quote?: string;
    offset?: number;
  } => ({
    pin: typeof search.pin === "string" ? search.pin.slice(0, 36) : undefined,
    pinVersion:
      Number.isSafeInteger(Number(search.pinVersion)) &&
      Number(search.pinVersion) > 0
        ? Number(search.pinVersion)
        : undefined,
    view:
      search.view === "next" || search.view === "sources"
        ? search.view
        : undefined,
    source:
      typeof search.source === "string"
        ? search.source.slice(0, 200)
        : undefined,
    q: typeof search.q === "string" ? search.q.slice(0, 200) : undefined,
    cursor:
      typeof search.cursor === "string"
        ? search.cursor.slice(0, 2000)
        : undefined,
    searchCursor:
      typeof search.searchCursor === "string"
        ? search.searchCursor.slice(0, 2000)
        : undefined,
    version:
      typeof search.version === "string"
        ? search.version.slice(0, 128)
        : undefined,
    quote:
      typeof search.quote === "string" ? search.quote.slice(0, 80) : undefined,
    offset:
      Number.isSafeInteger(Number(search.offset)) && Number(search.offset) >= 0
        ? Number(search.offset)
        : undefined,
  }),
  component: function ContextRoute() {
    const { sessionId } = Route.useParams();
    return <ChatContextPage key={sessionId} sessionId={sessionId} />;
  },
});
