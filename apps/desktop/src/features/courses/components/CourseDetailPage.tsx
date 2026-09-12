import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { buttonVariants, Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import { CourseChatTab } from "@/features/courses/components/CourseChatTab";
import { CourseCoreStatsCard } from "@/features/courses/components/CourseCoreStatsCard";
import { CourseEditSheet } from "@/features/courses/components/CourseEditSheet";
import { CourseHero } from "@/features/courses/components/CourseHero";
import { CourseInfoPanel } from "@/features/courses/components/CourseInfoPanel";
import { CourseInsightCard } from "@/features/courses/components/CourseInsightCard";
import { CourseKnowledgeGraph } from "@/features/courses/components/CourseKnowledgeGraph";
import { CourseLearningContextCard } from "@/features/courses/components/CourseLearningContextCard";
import { CourseMasteryGpsCard } from "@/features/courses/components/CourseMasteryGpsCard";
import { CourseQuoteCard } from "@/features/courses/components/CourseQuoteCard";
import { CourseRecentRecordsCard } from "@/features/courses/components/CourseRecentRecordsCard";
import { CourseRecommendedPointsCard } from "@/features/courses/components/CourseRecommendedPointsCard";
import { CourseRecordsPanel } from "@/features/courses/components/CourseRecordsPanel";
import { DeleteCourseDialog } from "@/features/courses/components/DeleteCourseDialog";
import { KnowledgeGpsTab } from "@/features/courses/components/KnowledgeGpsTab";
import { KnowledgeMapTab } from "@/features/courses/components/KnowledgeMapTab";
import { QuizTestsPanel } from "@/features/quiz-tests/components/QuizTestsPanel";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import { ApiError } from "@/services/http/client";

type CourseDetailPageProps = {
  courseId: string;
  tab: CourseTab;
  initialEditing?: boolean;
  onTabChange: (tab: CourseTab) => void;
  onDeleted: () => void | Promise<void>;
};

export function CourseDetailPage({
  courseId,
  tab,
  initialEditing = false,
  onTabChange,
  onDeleted,
}: CourseDetailPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(initialEditing);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const course = useQuery({
    queryKey: courseKeys.detail(courseId),
    queryFn: () => courseApi.get(courseId),
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404
        ? false
        : failureCount < 2,
  });
  const records = useQuery({
    queryKey: recordKeys.courseList(courseId),
    queryFn: () => recordApi.listForCourse(courseId),
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
  const latestRecordId = [...(records.data ?? [])].sort((left, right) =>
    right.created_at.localeCompare(left.created_at),
  )[0]?.id;

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full min-w-0 flex-col py-8">
      <nav
        aria-label={t("spaces.courseDetail.breadcrumb.label")}
        className="text-label text-ink-muted flex min-w-0 items-center gap-1.5"
      >
        <Link to="/spaces" className="hover:text-ink-strong shrink-0">
          {t("nav.spaces")}
        </Link>
        <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="shrink-0">
          {t("spaces.courseDetail.breadcrumb.myCourses")}
        </span>
        <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
        <span
          aria-current="page"
          className="text-ink-strong min-w-0 truncate font-medium"
          title={detail.name}
        >
          {detail.name}
        </span>
      </nav>

      <CourseHero
        course={detail}
        latestRecordId={latestRecordId}
        className="mt-4"
      />

      <Tabs
        value={tab}
        onValueChange={(value) => onTabChange(asCourseTab(value))}
        className="mt-6 min-w-0"
      >
        <TabsList
          variant="line"
          className="border-border [&_[data-slot=tabs-trigger][data-active]]:text-ink-strong gap-1 overflow-x-auto border-b pb-2 [&_[data-slot=tabs-trigger][data-active]::after]:opacity-100"
        >
          <TabsTrigger value="overview">
            {t("spaces.detail.tabs.overview")}
          </TabsTrigger>
          <TabsTrigger value="records">
            {t("spaces.detail.tabs.records")}
          </TabsTrigger>
          <TabsTrigger value="tests">
            {t("spaces.detail.tabs.tests")}
          </TabsTrigger>
          <TabsTrigger value="map">{t("spaces.detail.tabs.map")}</TabsTrigger>
          <TabsTrigger value="gps">{t("spaces.detail.tabs.gps")}</TabsTrigger>
          <TabsTrigger value="chat">{t("spaces.detail.tabs.chat")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="view-switch-enter mt-5">
          <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(16.5rem,21vw,19rem)]">
            <div className="@container min-w-0">
              <div className="grid min-w-0 gap-5 @2xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
                <div className="flex min-w-0 flex-col gap-5">
                  <CourseCoreStatsCard course={detail} />
                  <CourseKnowledgeGraph course={detail} />
                  <CourseRecentRecordsCard
                    courseId={courseId}
                    onViewAll={() => onTabChange("records")}
                  />
                </div>
                <div className="flex min-w-0 flex-col gap-5">
                  <CourseLearningContextCard course={detail} />
                  <CourseMasteryGpsCard
                    course={detail}
                    onViewAll={() => onTabChange("gps")}
                  />
                  <CourseInsightCard
                    course={detail}
                    onOpenChat={() => void navigate({ to: "/chat" })}
                  />
                  <CourseRecommendedPointsCard course={detail} />
                </div>
              </div>
            </div>
            <aside
              className="min-w-0"
              aria-label={t("spaces.detail.infoTitle")}
            >
              <div className="flex flex-col gap-5 xl:sticky xl:top-6">
                <CourseInfoPanel
                  course={detail}
                  records={records.data ?? []}
                  onEdit={() => setEditOpen(true)}
                  onDelete={() => setDeleteOpen(true)}
                />
                <CourseQuoteCard />
              </div>
            </aside>
          </div>
        </TabsContent>

        <TabsContent value="records" className="view-switch-enter mt-5">
          <CourseRecordsPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="tests" className="view-switch-enter mt-5">
          <QuizTestsPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="map" className="view-switch-enter mt-5">
          <KnowledgeMapTab course={detail} />
        </TabsContent>

        <TabsContent value="gps" className="view-switch-enter mt-5">
          <KnowledgeGpsTab course={detail} />
        </TabsContent>

        <TabsContent value="chat" className="view-switch-enter mt-5">
          <CourseChatTab
            course={detail}
            onOpenChat={() => void navigate({ to: "/chat" })}
          />
        </TabsContent>
      </Tabs>

      <CourseEditSheet
        course={detail}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <DeleteCourseDialog
        course={detail}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={onDeleted}
      />
    </section>
  );
}
