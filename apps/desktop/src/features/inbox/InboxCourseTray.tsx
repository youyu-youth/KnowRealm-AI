import { Link } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Folder, FolderOpen, Info } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
  type MouseEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { AppTooltip } from "@/components/common/AppTooltip";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useActiveCourses } from "@/features/courses/api/queries";

export function InboxCourseTray({
  children,
  dragging,
  canClassify,
  disabled,
  onClassify,
  onDrop,
}: {
  children: ReactNode;
  dragging: boolean;
  canClassify: boolean;
  disabled: boolean;
  onClassify: (courseId: string) => void;
  onDrop: (event: DragEvent<HTMLElement>, courseId: string) => void;
}) {
  const { t } = useTranslation();
  const { courses, isPending, isError } = useActiveCourses();
  const [hoveredCourse, setHoveredCourse] = useState<string | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [scrollState, setScrollState] = useState({
    previous: false,
    next: false,
  });
  const updateScroll = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const previous = track.scrollLeft > 1;
    const next = track.scrollLeft + track.clientWidth < track.scrollWidth - 1;
    setScrollState((current) =>
      current.previous === previous && current.next === next
        ? current
        : { previous, next },
    );
  }, []);
  useEffect(() => {
    updateScroll();
    const track = trackRef.current;
    if (!track) return;
    const observer = new ResizeObserver(updateScroll);
    observer.observe(track);
    return () => observer.disconnect();
  }, [courses.length, isPending, isError, updateScroll]);
  function scrollCourses(
    direction: number,
    event: MouseEvent<HTMLButtonElement>,
  ) {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({
      left: direction * track.clientWidth,
      behavior:
        event.detail === 0 ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
    });
  }
  return (
    <section
      className="inbox-course-tray"
      data-active={dragging || canClassify || undefined}
      aria-label={t("inbox.workspace.coursesTitle")}
    >
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 className="text-section text-ink font-semibold">
          {t("inbox.workspace.coursesTitle")}
        </h2>
        <p className="inbox-course-hint text-body-dense text-muted-foreground min-w-0 flex-1">
          {t(
            dragging
              ? "inbox.workspace.dropHint"
              : "inbox.workspace.coursesHint",
          )}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            nativeButton={false}
            variant="ghost"
            size="sm"
            render={<Link to="/spaces" />}
          >
            {t("inbox.workspace.allCourses")}
            <ArrowRight aria-hidden="true" className="size-3.5" />
          </Button>
          <AppTooltip label={t("inbox.workspace.previousCourses")} side="top">
            <Button
              variant="outline"
              size="icon-sm"
              disabled={!scrollState.previous}
              aria-label={t("inbox.workspace.previousCourses")}
              onClick={(event) => scrollCourses(-1, event)}
            >
              <ArrowLeft aria-hidden="true" />
            </Button>
          </AppTooltip>
          <AppTooltip label={t("inbox.workspace.nextCourses")} side="top">
            <Button
              variant="outline"
              size="icon-sm"
              disabled={!scrollState.next}
              aria-label={t("inbox.workspace.nextCourses")}
              onClick={(event) => scrollCourses(1, event)}
            >
              <ArrowRight aria-hidden="true" />
            </Button>
          </AppTooltip>
        </div>
        <div className="min-w-0">{children}</div>
      </div>
      {isPending ? (
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("sidebar.courses.loading")}
        </p>
      ) : isError ? (
        <p className="text-body text-destructive">
          {t("sidebar.courses.unavailable")}
        </p>
      ) : (
        <div
          ref={trackRef}
          className="inbox-course-grid"
          onScroll={updateScroll}
          role="group"
          aria-label={t("inbox.workspace.coursesTitle")}
        >
          {courses.map((course) => (
            <Button
              key={course.id}
              variant="ghost"
              className="inbox-course-target border-border bg-surface-raised hover:border-inbox-accent hover:bg-inbox-soft hover:text-foreground aria-disabled:hover:border-border aria-disabled:hover:bg-surface-raised data-drop-active:border-inbox-accent data-drop-active:bg-inbox-soft data-drop-active:outline-inbox-accent h-auto gap-3 rounded-lg border p-3 data-dragging:border-dashed data-drop-active:outline"
              data-drop-active={
                (dragging && hoveredCourse === course.id) || undefined
              }
              data-dragging={dragging || undefined}
              aria-label={t("inbox.workspace.classifyInto", {
                course: course.name,
              })}
              title={course.name}
              aria-disabled={disabled || (!canClassify && !dragging)}
              onClick={() => {
                if (!disabled && canClassify) onClassify(course.id);
              }}
              onDragOver={(event) => {
                if (
                  !dragging ||
                  disabled ||
                  !event.dataTransfer.types.includes(
                    "application/x-knowrealm-inbox",
                  )
                )
                  return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                setHoveredCourse(course.id);
              }}
              onDragLeave={(event) => {
                if (
                  !event.currentTarget.contains(
                    event.relatedTarget instanceof Node
                      ? event.relatedTarget
                      : null,
                  )
                )
                  setHoveredCourse(null);
              }}
              onDrop={(event) => {
                setHoveredCourse(null);
                if (!dragging || disabled) return;
                onDrop(event, course.id);
              }}
            >
              <span className="inbox-course-icon">
                {dragging && hoveredCourse === course.id ? (
                  <FolderOpen aria-hidden="true" className="size-5" />
                ) : (
                  <Folder aria-hidden="true" className="size-5" />
                )}
              </span>
              <span className="min-w-0 text-left">
                <span className="text-body text-ink line-clamp-2 font-medium break-words whitespace-normal">
                  {course.name}
                </span>
                <span className="text-label text-muted-foreground mt-1 block whitespace-normal">
                  {t(
                    dragging && hoveredCourse === course.id
                      ? "inbox.workspace.dropHint"
                      : canClassify
                        ? "inbox.workspace.courseTargetReady"
                        : "inbox.workspace.courseTargetHint",
                  )}
                </span>
              </span>
              <ArrowRight
                aria-hidden="true"
                className="inbox-course-arrow size-4 shrink-0"
              />
            </Button>
          ))}
          {courses.length === 0 ? (
            <p className="text-body-dense text-muted-foreground py-4">
              {t("inbox.workspace.createCourse")}
            </p>
          ) : null}
        </div>
      )}
      <p className="text-label text-muted-foreground mt-3 flex items-start gap-2">
        <Info aria-hidden="true" className="size-4 shrink-0" />
        {t("inbox.workspace.classifyNotice")}
      </p>
    </section>
  );
}
