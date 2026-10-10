import {
  BookOpen,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Leaf,
  Plus,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { Course, LearningContext } from "@/features/courses/api/types";
import { CourseCard } from "@/features/courses/components/CourseCard";
import { learningContextLabelKeys } from "@/features/courses/courseOptions";

const contexts = ["CAREER", "SCHOOL", "INTEREST"] as const;
const icons = { CAREER: BriefcaseBusiness, SCHOOL: BookOpen, INTEREST: Leaf };

type CourseTracksProps = {
  courses: Course[];
  context?: LearningContext;
  onCreate: (context: LearningContext) => void;
  onOpenCourse: (id: string) => void;
  onEditCourse: (id: string) => void;
  onDeleteCourse: (course: Course) => void;
};

export function CourseTracks(props: CourseTracksProps) {
  return (
    <div className="grid gap-3">
      {contexts
        .filter((context) => !props.context || props.context === context)
        .map((context) => (
          <CourseTrack
            key={context}
            {...props}
            context={context}
            courses={props.courses.filter(
              (course) => course.learning_context === context,
            )}
          />
        ))}
    </div>
  );
}

function CourseTrack({
  courses,
  context,
  onCreate,
  onOpenCourse,
  onEditCourse,
  onDeleteCourse,
}: CourseTracksProps & { context: LearningContext }) {
  const { t } = useTranslation();
  const rail = useRef<HTMLDivElement>(null);
  const [canScroll, setCanScroll] = useState({ back: false, forward: false });
  const Icon = icons[context];
  const title = t(learningContextLabelKeys[context]);

  const updateScroll = useCallback((element: HTMLDivElement) => {
    const back = element.scrollLeft > 1;
    const forward =
      element.scrollLeft + element.clientWidth < element.scrollWidth - 1;
    setCanScroll((current) =>
      current.back === back && current.forward === forward
        ? current
        : { back, forward },
    );
  }, []);
  const attachRail = useCallback(
    (element: HTMLDivElement | null) => {
      rail.current = element;
      if (!element || courses.length === 0) return;
      updateScroll(element);
      const observer = new ResizeObserver(() => updateScroll(element));
      observer.observe(element);
      return () => observer.disconnect();
    },
    [updateScroll, courses.length],
  );

  function scroll(direction: number, pointerInitiated: boolean) {
    const element = rail.current;
    if (element)
      element.scrollBy({
        left: direction * element.clientWidth,
        behavior:
          pointerInitiated &&
          !window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "smooth"
            : "instant",
      });
  }

  return (
    <section className="spaces-track" aria-label={title}>
      <header className="spaces-track-heading">
        <h2 className="text-spaces-section text-ink-strong flex flex-wrap items-center gap-2 font-semibold">
          <Icon className="size-6 shrink-0" aria-hidden="true" />
          {title}
          <span className="text-body text-ink-muted font-medium tabular-nums">
            {courses.length}
          </span>
        </h2>
        <p className="text-body text-ink-muted mt-2">
          {t(`spaces.tracks.description.${context}`)}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          aria-label={t("spaces.tracks.createIn", { context: title })}
          onClick={() => onCreate(context)}
        >
          <Plus aria-hidden="true" />
          {t("spaces.create")}
        </Button>
        <div
          className="mt-3 flex items-center gap-1"
          role="group"
          aria-label={t("spaces.tracks.browse", { context: title })}
        >
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={t("spaces.tracks.previous", { context: title })}
            disabled={!canScroll.back}
            onClick={(event) => scroll(-1, event.detail > 0)}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={t("spaces.tracks.next", { context: title })}
            disabled={!canScroll.forward}
            onClick={(event) => scroll(1, event.detail > 0)}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </div>
      </header>
      {courses.length ? (
        <div
          ref={attachRail}
          onScroll={(event) => updateScroll(event.currentTarget)}
          className="spaces-track-courses"
          role="region"
          aria-label={t("spaces.tracks.browse", { context: title })}
          tabIndex={0}
        >
          {courses.map((course) => (
            <CourseCard
              key={course.id}
              course={course}
              onOpen={() => onOpenCourse(course.id)}
              onEdit={() => onEditCourse(course.id)}
              onDelete={() => onDeleteCourse(course)}
            />
          ))}
        </div>
      ) : (
        <p className="text-body text-ink-muted py-8">
          {t("spaces.tracks.empty")}
        </p>
      )}
    </section>
  );
}
