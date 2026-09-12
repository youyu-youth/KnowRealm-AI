import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import type { CourseDetail } from "@/features/courses/api/types";
import { CourseKnowledgeGraph } from "@/features/courses/components/CourseKnowledgeGraph";

/** 课程脑图标签页：放大版知识概念图谱（示意）。 */
export function KnowledgeMapTab({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <CourseKnowledgeGraph
        course={course}
        titleKey="spaces.courseDetail.graph.tabTitle"
        heightClass="h-[30rem]"
      />
      <SurfaceCard title={t("spaces.courseDetail.map.descriptionTitle")}>
        <p className="text-body-dense text-ink-muted max-w-reading mt-2">
          {t("spaces.courseDetail.map.description")}
        </p>
      </SurfaceCard>
    </div>
  );
}
