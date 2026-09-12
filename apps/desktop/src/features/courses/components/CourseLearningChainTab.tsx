import { useQuery } from "@tanstack/react-query";
import { Route } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import type { CourseDetail } from "@/features/courses/api/types";
import { buildLearningChain } from "@/features/courses/courseLearningChain";
import { CourseLearningFlowChart } from "@/features/courses/components/CourseLearningFlowChart";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";

/** 学习链标签页：真实记录状态派生的阶段流转（桑基）+ 文字摘要。 */
export function CourseLearningChainTab({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const records = useQuery({
    queryKey: recordKeys.courseList(course.id),
    queryFn: () => recordApi.listForCourse(course.id),
  });

  if (records.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.records.loading")}
      </p>
    );
  }

  if (records.isError) {
    return (
      <div role="alert">
        <h3 className="text-section font-section text-ink">
          {t("spaces.records.errorTitle")}
        </h3>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {t("spaces.records.errorDescription")}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void records.refetch()}
        >
          {t("spaces.records.retry")}
        </Button>
      </div>
    );
  }

  const chain = buildLearningChain(records.data);

  if (chain.total === 0) {
    return (
      <Empty className="items-start rounded-none p-0 text-start">
        <EmptyHeader className="items-start text-start">
          <Route
            className="text-ink-faint size-5"
            aria-hidden="true"
            strokeWidth={1.5}
          />
          <h3 className="text-section font-section text-ink">
            {t("spaces.courseDetail.chain.emptyTitle")}
          </h3>
          <EmptyDescription className="max-w-reading text-body">
            {t("spaces.courseDetail.chain.emptyDescription")}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <CourseLearningFlowChart courseName={course.name} chain={chain} />
      <p className="text-label text-ink-muted">
        {t("spaces.courseDetail.chain.note")}
      </p>
    </div>
  );
}
