import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/features/settings/SettingsPage";
import {
  isSettingsSection,
  type SettingsSection,
} from "@/features/settings/sections";

export const Route = createFileRoute("/settings")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { section?: SettingsSection } => ({
    section: isSettingsSection(search.section) ? search.section : undefined,
  }),
  component: function SettingsRoute() {
    const search = Route.useSearch();
    const navigate = Route.useNavigate();

    return (
      <SettingsPage
        section={search.section ?? "profile"}
        onSectionChange={(section) =>
          void navigate({
            search: section === "profile" ? {} : { section },
          })
        }
      />
    );
  },
});
