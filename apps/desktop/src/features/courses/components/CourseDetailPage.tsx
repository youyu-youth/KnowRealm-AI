import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, buttonVariants } from "@/components/ui/button";
import { appToast } from "@/components/common/appToastManager";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import type { MasteryStatus } from "@/features/courses/api/types";
import { courseKeys } from "@/features/courses/api/keys";
import { courseApi } from "@/features/courses/api/courses";
import { ApiError } from "@/services/http/client";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import { CourseBrainRoseCard } from "@/features/courses/components/CourseBrainRoseCard";
import { CourseBrainTab } from "@/features/courses/components/CourseBrainTab";
import { CourseChatTab } from "@/features/courses/components/CourseChatTab";
import { CourseCoreOverview } from "@/features/courses/components/CourseCoreOverview";
import { CourseEditSheet } from "@/features/courses/components/CourseEditSheet";
import { CourseHero } from "@/features/courses/components/CourseHero";
import { CourseInfoPanel } from "@/features/courses/components/CourseInfoPanel";
import { CourseInsightCard } from "@/features/courses/components/CourseInsightCard";
import { CourseLearningChainTab } from "@/features/courses/components/CourseLearningChainTab";
import { CourseMasteryGpsCard } from "@/features/courses/components/CourseMasteryGpsCard";
import { CourseRecentRecordsCard } from "@/features/courses/components/CourseRecentRecordsCard";
import { CourseRecommendedPointsCard } from "@/features/courses/components/CourseRecommendedPointsCard";
import { CourseRecordsPanel } from "@/features/courses/components/CourseRecordsPanel";
import { ArchiveCourseDialog } from "@/features/courses/components/ArchiveCourseDialog";
import { DeleteCourseDialog } from "@/features/courses/components/DeleteCourseDialog";
import { KnowledgeGpsTab } from "@/features/courses/components/KnowledgeGpsTab";
import { QuizTestsPanel } from "@/features/quiz-tests/components/QuizTestsPanel";

type CourseDetailPageProps = {
  courseId: string;
  tab: CourseTab;
  initialEditing?: boolean;
  masteryStatus?: MasteryStatus;
  onTabChange: (tab: CourseTab) => void;
  onMasteryStatusChange: (status?: MasteryStatus) => void;
  onDeleted: () => void | Promise<void>;
};

export function CourseDetailPage({
  courseId,
  tab,
  initialEditing = false,
  masteryStatus,
  onTabChange,
  onMasteryStatusChange,
  onDeleted,
}: CourseDetailPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(initialEditing);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const restoreCourse = useMutation({
    mutationFn: () => courseApi.unarchive(courseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: courseKeys.detail(courseId),
          exact: true,
          refetchType: "none",
        }),
        queryClient.invalidateQueries({ queryKey: courseKeys.lists() }),
      ]);
      appToast.add({ description: t("spaces.archive.restoreDone") });
    },
    onError: (error) => {
      appToast.add({
        description:
          error instanceof Error
            ? error.message
            : t("spaces.archive.restoreFailed"),
      });
    },
  });
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
    <section className="work-surface-enter flex h-full min-h-0 min-w-0 flex-col">
      <div className="px-content shrink-0 pt-6">
        <div className="max-w-workbench mx-auto min-w-0">
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
            onOpenInfo={() => setInfoOpen(true)}
            className="mt-4"
          />
        </div>
      </div>

      <Tabs
        value={tab}
        onValueChange={(value) => onTabChange(asCourseTab(value))}
        className="mt-5 min-h-0 flex-1"
      >
        <div className="px-content shrink-0">
          <div className="max-w-workbench mx-auto min-w-0">
            <TabsList
              variant="line"
              className="border-border [&_[data-slot=tabs-trigger][data-active]]:text-ink-strong gap-1 overflow-x-auto border-b pb-2 [&_[data-slot=tabs-trigger][data-active]::after]:opacity-100"
            >
              <TabsTrigger value="overview">
                {t("spaces.detail.tabs.overview")}
              </TabsTrigger>
              <TabsTrigger value="chain">
                {t("spaces.detail.tabs.chain")}
              </TabsTrigger>
              <TabsTrigger value="records">
                {t("spaces.detail.tabs.records")}
              </TabsTrigger>
              <TabsTrigger value="tests">
                {t("spaces.detail.tabs.tests")}
              </TabsTrigger>
              <TabsTrigger value="map">
                {t("spaces.detail.tabs.map")}
              </TabsTrigger>
              <TabsTrigger value="gps">
                {t("spaces.detail.tabs.gps")}
              </TabsTrigger>
              <TabsTrigger value="chat">
                {t("spaces.detail.tabs.chat")}
              </TabsTrigger>
            </TabsList>
          </div>
        </div>

        <TabsContent
          value="overview"
          className="view-switch-enter min-h-0 flex-1"
        >
          <div className="px-content h-full min-h-0 pt-5 pb-6">
            <div className="max-w-workbench mx-auto grid h-full min-h-0 gap-6 xl:grid-cols-[minmax(0,1fr)_clamp(14rem,18vw,17rem)]">
              <div className="@container min-h-0 min-w-0 overflow-y-auto pr-1 pb-2">
                <div className="flex min-w-0 flex-col gap-6">
                  <CourseCoreOverview course={detail} />
                  <CourseBrainRoseCard course={detail} />
                  <div className="grid min-w-0 gap-6 @2xl:grid-cols-2">
                    <CourseRecentRecordsCard
                      courseId={courseId}
                      onViewAll={() => onTabChange("records")}
                    />
                    <CourseMasteryGpsCard
                      course={detail}
                      onViewAll={() => onTabChange("gps")}
                      onOpenBrain={() => onTabChange("map")}
                    />
                  </div>
                  <div className="grid min-w-0 gap-6 @2xl:grid-cols-2">
                    <CourseInsightCard
                      course={detail}
                      onOpenChat={() => void navigate({ to: "/chat" })}
                    />
                    <CourseRecommendedPointsCard course={detail} />
                  </div>
                </div>
              </div>
              <aside
                className="border-border-subtle hidden min-h-0 min-w-0 overflow-y-auto border-l pb-2 pl-5 xl:block"
                aria-label={t("spaces.detail.infoTitle")}
              >
                <CourseInfoPanel
                  course={detail}
                  records={records.data ?? []}
                  onEdit={() => setEditOpen(true)}
                  onDelete={() => setDeleteOpen(true)}
                  onArchive={() => setArchiveOpen(true)}
                  onRestore={() => restoreCourse.mutate()}
                  restorePending={restoreCourse.isPending}
                />
              </aside>
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="chain"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <CourseLearningChainTab course={detail} />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="records"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <CourseRecordsPanel courseId={courseId} />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="tests"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <QuizTestsPanel courseId={courseId} />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="map"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <CourseBrainTab course={detail} />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="gps"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <KnowledgeGpsTab
                course={detail}
                statusFilter={masteryStatus}
                onStatusFilterChange={onMasteryStatusChange}
                onOpenBrain={() => onTabChange("map")}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="chat"
          className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
        >
          <div className="px-content">
            <div className="max-w-workbench mx-auto pt-5 pb-8">
              <CourseChatTab course={detail} />
            </div>
          </div>
        </TabsContent>
      </Tabs>

      <Sheet open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent className="sm:max-w-md">
          <SheetHeader className="sr-only">
            <SheetTitle>{t("spaces.detail.infoTitle")}</SheetTitle>
            <SheetDescription>
              {t("spaces.courseDetail.info.sheetDescription")}
            </SheetDescription>
          </SheetHeader>
          <SheetBody>
            <CourseInfoPanel
              course={detail}
              records={records.data ?? []}
              onEdit={() => {
                setInfoOpen(false);
                setEditOpen(true);
              }}
              onDelete={() => {
                setInfoOpen(false);
                setDeleteOpen(true);
              }}
              onArchive={() => {
                setInfoOpen(false);
                setArchiveOpen(true);
              }}
              onRestore={() => restoreCourse.mutate()}
              restorePending={restoreCourse.isPending}
            />
          </SheetBody>
        </SheetContent>
      </Sheet>

      <CourseEditSheet
        course={detail}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <ArchiveCourseDialog
        course={detail}
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
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
