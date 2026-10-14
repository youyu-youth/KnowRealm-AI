import { Link } from "@tanstack/react-router";
import { BookOpenText, ChevronDown, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MainNavigation } from "@/components/layout/MainNavigation";
import { SidebarUserArea } from "@/components/layout/SidebarUserArea";
import { selectSidebarCourses } from "@/components/layout/selectSidebarCourses";
import { AppTooltip } from "@/components/common/AppTooltip";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useActiveCourses } from "@/features/courses/api/queries";

export function TopNavigation({ courseId }: { courseId?: string }) {
  const { t } = useTranslation();
  const courses = useActiveCourses();
  const recent = selectSidebarCourses(courses.courses, courseId);

  return (
    <div className="bg-sidebar flex min-w-0 shrink-0 items-center gap-2 pb-2">
      <MainNavigation />
      <div className="flex shrink-0 items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" size="sm" />}
            aria-label={t("nav.courses.label")}
          >
            <BookOpenText data-icon="inline-start" aria-hidden="true" />
            <span className="max-sm:sr-only">{t("nav.courses.label")}</span>
            <ChevronDown data-icon="inline-end" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-w-xs">
            <DropdownMenuGroup>
              {courses.isPending || courses.isError ? (
                <DropdownMenuItem disabled>
                  {t(
                    courses.isPending
                      ? "nav.courses.loading"
                      : "nav.courses.unavailable",
                  )}
                </DropdownMenuItem>
              ) : (
                recent.map((course) => (
                  <DropdownMenuItem
                    key={course.id}
                    render={
                      <Link
                        to="/spaces/$courseId"
                        params={{ courseId: course.id }}
                        search={{ tab: "overview" }}
                        activeProps={{ "aria-current": "page" }}
                      />
                    }
                    title={course.name}
                  >
                    <span className="truncate">{course.name}</span>
                  </DropdownMenuItem>
                ))
              )}
              <DropdownMenuItem render={<Link to="/spaces" />}>
                {t("nav.courses.viewAll")}
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <SidebarUserArea compact />
        <AppTooltip label={t("nav.settings")}>
          <Link
            to="/settings"
            aria-label={t("nav.settings")}
            className="hover:bg-surface-subtle focus-visible:ring-ring/40 text-muted-foreground flex size-9 items-center justify-center rounded-md focus-visible:ring-3"
            activeProps={{ className: "bg-surface-subtle text-ink-strong" }}
          >
            <Settings className="size-4" aria-hidden="true" />
          </Link>
        </AppTooltip>
      </div>
    </div>
  );
}
