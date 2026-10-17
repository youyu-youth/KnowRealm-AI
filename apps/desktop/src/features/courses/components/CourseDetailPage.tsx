import { learningPlanKeys } from "@/features/learningPlan/api/keys";
import { Link } from "@tanstack/react-router";
import {
  BookOpen,
  CalendarDays,
  ChevronRight,
  Files,
  FileText,
  GitBranch,
  Map,
  MessagesSquare,
  Network,
  NotebookPen,
} from "lucide-react";
import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, buttonVariants } from "@/components/ui/button";
import { appToast } from "@/components/common/appToastManager";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import type { MasteryStatus } from "@/features/courses/api/types";
import { courseKeys } from "@/features/courses/api/keys";
import { courseApi } from "@/features/courses/api/courses";
import { ApiError } from "@/services/http/client";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import { CourseBrainTab } from "@/features/courses/components/CourseBrainTab";
import { CourseChatTab } from "@/features/courses/components/CourseChatTab";
import { CourseEditSheet } from "@/features/courses/components/CourseEditSheet";
import { CourseHero } from "@/features/courses/components/CourseHero";
import { CourseInfoPanel } from "@/features/courses/components/CourseInfoPanel";
import { CourseSidebarActions } from "@/features/courses/components/CourseSidebarActions";
import { ArchiveCourseDialog } from "@/features/courses/components/ArchiveCourseDialog";
import { DeleteCourseDialog } from "@/features/courses/components/DeleteCourseDialog";
import { CourseLearningChainTab } from "@/features/courses/components/CourseLearningChainTab";
import { CourseOverview } from "@/features/courses/components/CourseOverview";
import { CourseCaptureDock } from "@/features/courses/components/CourseCaptureDock";
import { CaptureActionsContext } from "@/components/layout/captureActionsContext";
import "@/features/courses/courseDetail.css";
import { CourseRecordsPanel } from "@/features/courses/components/CourseRecordsPanel";
import { KnowledgeGpsTab } from "@/features/courses/components/KnowledgeGpsTab";
import { LearningPlanTab } from "@/features/learningPlan/components/LearningPlanTab";
import { QuizTestsPanel } from "@/features/quiz-tests/components/QuizTestsPanel";
import { SharedRefsTab } from "@/features/sharedRefs/components/SharedRefsTab";

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
  const openCapture = useContext(CaptureActionsContext);
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(initialEditing);
  const [infoOpen, setInfoOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const restoreCourse = useMutation({
    mutationFn: () => courseApi.unarchive(courseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: courseKeys.detail(courseId),
          exact: true,
        }),
        queryClient.invalidateQueries({ queryKey: learningPlanKeys.all }),
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

  return (
    <section className="course-detail">
      <Tabs
        value={tab}
        orientation="vertical"
        onValueChange={(value) => onTabChange(asCourseTab(value))}
        className="course-workspace"
      >
        <aside
          className="course-sidebar"
          aria-label={t("spaces.detail.infoTitle")}
        >
          <div className="course-sidebar-content">
            <CourseHero
              course={detail}
              onOpenInfo={() => setInfoOpen(true)}
              onAddMaterials={() => openCapture?.("capture.import")}
            />
            <TabsList
              variant="line"
              className="course-tabs"
              aria-label={t("spaces.courseDetail.navigation")}
            >
              <TabsTrigger value="overview">
                <BookOpen aria-hidden="true" />
                {t("spaces.detail.tabs.overview")}
              </TabsTrigger>
              <TabsTrigger value="chain">
                <GitBranch aria-hidden="true" />
                {t("spaces.detail.tabs.chain")}
              </TabsTrigger>
              <TabsTrigger value="plan">
                <CalendarDays aria-hidden="true" />
                {t("spaces.detail.tabs.plan")}
              </TabsTrigger>
              <TabsTrigger value="shared">
                <Files aria-hidden="true" />
                {t("spaces.detail.tabs.shared")}
              </TabsTrigger>
              <TabsTrigger value="records">
                <FileText aria-hidden="true" />
                {t("spaces.detail.tabs.records")}
              </TabsTrigger>
              <TabsTrigger value="tests">
                <NotebookPen aria-hidden="true" />
                {t("spaces.detail.tabs.tests")}
              </TabsTrigger>
              <TabsTrigger value="map">
                <Network aria-hidden="true" />
                {t("spaces.detail.tabs.map")}
              </TabsTrigger>
              <TabsTrigger value="gps">
                <Map aria-hidden="true" />
                {t("spaces.detail.tabs.gps")}
              </TabsTrigger>
              <TabsTrigger value="chat">
                <MessagesSquare aria-hidden="true" />
                {t("spaces.detail.tabs.chat")}
              </TabsTrigger>
            </TabsList>
          </div>
          <CourseSidebarActions
            course={detail}
            onEdit={() => setEditOpen(true)}
            onArchive={() => setArchiveOpen(true)}
            onDelete={() => setDeleteOpen(true)}
            onRestore={() => restoreCourse.mutate()}
            restorePending={restoreCourse.isPending}
          />
        </aside>
        <div className="course-workspace-main">
          <div className="course-breadcrumb">
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
          </div>

          <TabsContent
            value="overview"
            className="view-switch-enter min-h-0 flex-1"
          >
            <CourseOverview course={detail} onTabChange={onTabChange} />
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
            value="plan"
            className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
          >
            <div className="px-content">
              <div className="max-w-workbench mx-auto pt-5 pb-8">
                <LearningPlanTab courseId={courseId} />
              </div>
            </div>
          </TabsContent>

          <TabsContent
            value="shared"
            className="view-switch-enter min-h-0 flex-1 overflow-y-auto"
          >
            <div className="px-content">
              <div className="max-w-workbench mx-auto pt-5 pb-8">
                <SharedRefsTab courseId={courseId} />
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
          <CourseCaptureDock course={detail} />
        </div>
      </Tabs>

      <Dialog open={infoOpen} onOpenChange={setInfoOpen}>
        <DialogContent className="max-h-dvh overflow-y-auto sm:max-w-lg">
          <DialogHeader className="sr-only">
            <DialogTitle>{t("spaces.detail.infoTitle")}</DialogTitle>
            <DialogDescription>
              {t("spaces.courseDetail.info.sheetDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="min-w-0 p-2 pt-6">
            <CourseInfoPanel
              course={detail}
              records={records.data ?? []}
              onEdit={() => {
                setInfoOpen(false);
                setEditOpen(true);
              }}
            />
          </div>
        </DialogContent>
      </Dialog>

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
