import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  courseLevelLabelKey,
  courseTypeLabelKeys,
  learningContextLabelKeys,
} from "@/features/courses/courseOptions";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import { CourseOverview } from "@/features/courses/components/CourseOverview";
import { CourseRecordsPanel } from "@/features/courses/components/CourseRecordsPanel";
import { ApiError } from "@/services/http/client";

type CourseDetailPageProps = {
  courseId: string;
  tab: CourseTab;
  onTabChange: (tab: CourseTab) => void;
  onDeleted: () => void | Promise<void>;
};

export function CourseDetailPage({
  courseId,
  tab,
  onTabChange,
  onDeleted,
}: CourseDetailPageProps) {
  const { t } = useTranslation();
  const course = useQuery({
    queryKey: courseKeys.detail(courseId),
    queryFn: () => courseApi.get(courseId),
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404
        ? false
        : failureCount < 2,
  });

  if (course.isPending) {
    return (
      <section className="max-w-workbench px-content mx-auto py-8">
        <p
          role="status"
          className="text-body text-muted-foreground flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.detail.loading")}
        </p>
      </section>
    );
  }

  if (course.isError) {
    const notFound =
      course.error instanceof ApiError && course.error.status === 404;
    return (
      <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col items-start py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {notFound
            ? t("spaces.detail.notFoundTitle")
            : t("spaces.detail.errorTitle")}
        </h1>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {notFound
            ? t("spaces.detail.notFoundDescription")
            : t("spaces.detail.errorDescription")}
        </p>
        {notFound ? (
          <Link
            to="/spaces"
            className={buttonVariants({
              variant: "outline",
              className: "mt-8",
            })}
          >
            {t("spaces.detail.backToSpaces")}
          </Link>
        ) : (
          <Button
            variant="outline"
            className="mt-8"
            onClick={() => void course.refetch()}
          >
            {t("spaces.detail.retry")}
          </Button>
        )}
      </section>
    );
  }

  const detail = course.data;
  const levelKey = courseLevelLabelKey(detail);

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col py-8">
      <Link
        to="/spaces"
        className="text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex items-center gap-1.5 rounded-sm transition-colors focus-visible:ring-3"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t("spaces.detail.backToSpaces")}
      </Link>

      <header className="mt-5">
        <h1 className="text-headline font-headline text-ink-strong">
          {detail.name}
        </h1>
        <p className="text-body text-muted-foreground mt-2">
          {t(learningContextLabelKeys[detail.learning_context])}
          {levelKey ? ` · ${t(levelKey)}` : null}
          {detail.course_type
            ? ` · ${t(courseTypeLabelKeys[detail.course_type])}`
            : null}
        </p>
      </header>

      <Tabs
        value={tab}
        onValueChange={(value) => onTabChange(asCourseTab(value))}
        className="mt-8"
      >
        <TabsList>
          <TabsTrigger value="overview">
            {t("spaces.detail.tabs.overview")}
          </TabsTrigger>
          <TabsTrigger value="records">
            {t("spaces.detail.tabs.records")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-6">
          <CourseOverview course={detail} onDeleted={onDeleted} />
        </TabsContent>
        <TabsContent value="records" className="mt-6">
          <CourseRecordsPanel />
        </TabsContent>
      </Tabs>
    </section>
  );
}
