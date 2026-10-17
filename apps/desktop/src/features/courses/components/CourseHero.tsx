import { Info, PlusCircle, Star } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { courseDetailSeed } from "@/features/courses/courseDetailInsights";
import { CourseMetaTags } from "@/features/courses/components/CourseMetaTags";
import { CourseStatusTag } from "@/features/courses/components/CourseCard";

/** 确定性封面：按课程 id 生成灰度渐变 + 同心纹样，不依赖外部资源。 */
function CourseCoverArt({ course }: { course: CourseDetail }) {
  const seed = courseDetailSeed(course.id);
  const palette = seed % 5;
  const from = `var(--course-cover-${palette}-from)`;
  const to = `var(--course-cover-${palette}-to)`;
  const gradientId = `course-cover-${course.id}`;
  const stroke = "var(--ink-strong)";
  return (
    <svg
      viewBox="0 0 160 120"
      role="img"
      aria-hidden="true"
      preserveAspectRatio="xMidYMid slice"
      className="h-full w-full"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
      </defs>
      <rect width="160" height="120" fill={`url(#${gradientId})`} />
      <g
        fill="none"
        stroke={stroke}
        strokeOpacity="var(--course-cover-opacity)"
      >
        <circle cx={24 + (seed % 40)} cy={26 + ((seed >>> 6) % 30)} r={34} />
        <circle cx={120 - ((seed >>> 9) % 40)} cy={92} r={46} />
        <circle cx={132} cy={22 + ((seed >>> 12) % 26)} r={20} />
        <path
          d={`M0 ${96 - ((seed >>> 15) % 24)} L160 ${10 + ((seed >>> 18) % 30)}`}
          strokeOpacity="0.07"
        />
      </g>
    </svg>
  );
}

type CourseHeroProps = {
  course: CourseDetail;
  onOpenInfo: () => void;
  onAddMaterials: () => void;
  className?: string;
};

export function CourseHero({
  course,
  onOpenInfo,
  onAddMaterials,
  className,
}: CourseHeroProps) {
  const { t } = useTranslation();
  const [following, setFollowing] = useState(false);

  const description =
    course.description?.trim() || t("spaces.detail.noDescription");

  return (
    <header className={`course-hero ${className ?? ""}`}>
      <div className="course-detail-cover">
        <CourseCoverArt course={course} />
        <span>
          {course.name.match(/[A-Za-z][A-Za-z0-9.+#-]*/)?.[0] ??
            course.name.slice(0, 6)}
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h1 className="course-name">{course.name}</h1>
            <CourseStatusTag course={course} />
          </div>
          <CourseMetaTags course={course} className="mt-2" />
          <p
            className="course-description text-body text-muted-foreground mt-2 line-clamp-2"
            title={description}
          >
            {description}
          </p>
        </div>
        <div className="course-hero-actions">
          <Button className="course-open-button" onClick={onOpenInfo}>
            <Info data-icon="inline-start" aria-hidden="true" />
            {t("spaces.courseDetail.hero.viewDetails")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            aria-pressed={following}
            onClick={() => setFollowing((current) => !current)}
          >
            <Star
              data-icon="inline-start"
              aria-hidden="true"
              className={following ? "fill-current" : undefined}
            />
            {following
              ? t("spaces.courseDetail.hero.following")
              : t("spaces.courseDetail.hero.follow")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={course.status === "ARCHIVED"}
            onClick={onAddMaterials}
          >
            <PlusCircle data-icon="inline-start" aria-hidden="true" />
            {t("spaces.courseDetail.hero.addMaterials")}
          </Button>
        </div>
      </div>
    </header>
  );
}
