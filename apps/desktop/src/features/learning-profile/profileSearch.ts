import { isMasteryStatus } from "@/features/courses/masteryStatus";
import type { MasteryStatus } from "@/features/courses/api/types";

export const profileTabs = ["concepts", "history", "goals", "memory"] as const;
export type ProfileTab = (typeof profileTabs)[number];
export type ProfileSearch = {
  tab?: ProfileTab;
  course?: string;
  concept?: string;
  status?: MasteryStatus;
  date?: string;
};

export function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function parseProfileSearch(
  search: Record<string, unknown>,
): ProfileSearch {
  const date =
    typeof search.date === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(search.date) &&
    localDateKey(new Date(`${search.date}T12:00:00`)) === search.date
      ? search.date
      : undefined;
  return {
    tab: profileTabs.find((tab) => tab === search.tab) ?? "concepts",
    course: typeof search.course === "string" ? search.course : undefined,
    concept: typeof search.concept === "string" ? search.concept : undefined,
    status: isMasteryStatus(search.status) ? search.status : undefined,
    date,
  };
}
