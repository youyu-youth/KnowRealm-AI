import { createFileRoute } from "@tanstack/react-router";
import { InboxPage } from "@/features/inbox/InboxPage";
import {
  isInboxStatusFilter,
  isInboxTypeFilter,
  type InboxSearch,
} from "@/features/inbox/inboxSearch";

export const Route = createFileRoute("/inbox")({
  validateSearch: (search: Record<string, unknown>): InboxSearch => ({
    q: typeof search.q === "string" && search.q.trim() ? search.q : undefined,
    type: isInboxTypeFilter(search.type) ? search.type : undefined,
    status: isInboxStatusFilter(search.status) ? search.status : undefined,
    page:
      typeof search.page === "number" &&
      Number.isInteger(search.page) &&
      search.page > 1
        ? search.page
        : undefined,
    record:
      typeof search.record === "string" && search.record
        ? search.record
        : undefined,
  }),
  component: function InboxRoute() {
    const search = Route.useSearch();
    const navigate = Route.useNavigate();

    return (
      <InboxPage
        search={search}
        onSearchChange={(next) =>
          void navigate({ search: next, replace: true })
        }
      />
    );
  },
});
