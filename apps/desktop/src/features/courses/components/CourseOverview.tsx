import type { CourseDetail } from "@/features/courses/api/types";
import { CourseCoreOverview } from "@/features/courses/components/CourseCoreOverview";
import { CourseRecentRecordsCard } from "@/features/courses/components/CourseRecentRecordsCard";
import { CourseBrainRoseCard } from "@/features/courses/components/CourseBrainRoseCard";
import { CourseInsightCard } from "@/features/courses/components/CourseInsightCard";
import { CourseMasteryGpsCard } from "@/features/courses/components/CourseMasteryGpsCard";
import { CourseRecommendedPointsCard } from "@/features/courses/components/CourseRecommendedPointsCard";
import type { CourseTab } from "@/features/courses/courseTabs";

export function CourseOverview({
  course,
  onTabChange,
}: {
  course: CourseDetail;
  onTabChange: (tab: CourseTab) => void;
}) {
  return (
    <div className="course-overview">
      <CourseCoreOverview course={course} />
      <div className="course-overview-columns">
        <div className="course-overview-column">
          <CourseRecentRecordsCard
            courseId={course.id}
            onViewAll={() => onTabChange("records")}
          />
          <CourseInsightCard
            course={course}
            onOpenChat={() => onTabChange("chat")}
          />
        </div>
        <div className="course-overview-column">
          <CourseBrainRoseCard course={course} />
          <CourseMasteryGpsCard
            course={course}
            onViewAll={() => onTabChange("gps")}
            onOpenBrain={() => onTabChange("map")}
          />
        </div>
      </div>
      <CourseRecommendedPointsCard course={course} />
    </div>
  );
}
