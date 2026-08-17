import { createFileRoute } from "@tanstack/react-router";
import { CoursesPage } from "@/features/courses/components/CoursesPage";

export const Route = createFileRoute("/spaces")({ component: SpacesPage });

export function SpacesPage() {
  return <CoursesPage />;
}
