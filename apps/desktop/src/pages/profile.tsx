import { createFileRoute } from "@tanstack/react-router";
import { LearningProfilePage } from "@/features/learning-profile/LearningProfilePage";
import { parseProfileSearch } from "@/features/learning-profile/profileSearch";

export const Route = createFileRoute("/profile")({
  validateSearch: parseProfileSearch,
  component: ProfileRoute,
});

export function ProfileRoute() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <LearningProfilePage
      search={search}
      onSearchChange={(patch) => {
        void navigate({ search: (previous) => ({ ...previous, ...patch }) });
      }}
    />
  );
}
