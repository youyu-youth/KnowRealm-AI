import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { BookOpen, SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import { LearningPlanTab } from "@/features/learningPlan/components/LearningPlanTab";
import { LearnerMemorySection } from "@/features/settings/LearnerMemorySection";
import {
  EXAMPLE_COURSE,
  exampleProfile,
} from "@/features/learning-profile/exampleProfile";
import { ProfileActivity } from "@/features/learning-profile/ProfileActivity";
import { ProfileMasterySummary } from "@/features/learning-profile/ProfileMasterySummary";
import { ProfileTimeline } from "@/features/learning-profile/ProfileTimeline";
import { ProfileConceptWorkspace } from "@/features/learning-profile/ProfileConceptWorkspace";
import {
  profileTabs,
  type ProfileSearch,
} from "@/features/learning-profile/profileSearch";
import "@/features/learning-profile/LearningProfile.css";

type Props = {
  search: ProfileSearch;
  onSearchChange: (patch: Partial<ProfileSearch>) => void;
};

export function LearningProfilePage({ search, onSearchChange }: Props) {
  const { t } = useTranslation();
  const [calendarOpen, setCalendarOpen] = useState(false);
  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
  });
  const active = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const course =
    active.find((item) => item.id === search.course) ??
    (!search.course ? active[0] : undefined);
  const example = search.course === EXAMPLE_COURSE;
  const courseId = example ? EXAMPLE_COURSE : course?.id;
  const mastery = useQuery({
    queryKey: courseKeys.mastery(courseId ?? ""),
    queryFn: () => courseApi.mastery(courseId ?? ""),
    enabled: !!courseId && !example,
  });
  const data = example ? exampleProfile(t) : mastery.data;
  const options = [
    ...active.map((item) => ({ value: item.id, label: item.name })),
    { value: EXAMPLE_COURSE, label: t("learningProfile.example.option") },
  ];
  return (
    <section className="profile-page text-ink min-h-full">
      <Button
        variant="ghost"
        className="profile-calendar-toggle m-3"
        aria-expanded={calendarOpen}
        aria-controls="profile-calendar"
        onClick={() => setCalendarOpen((open) => !open)}
      >
        {t("learningProfile.calendar.toggle")}
      </Button>
      <div className="profile-layout" data-calendar-open={calendarOpen}>
        <ProfileActivity
          date={search.date}
          onDateChange={(date) => onSearchChange({ date })}
        />
        <div className="profile-main min-w-0">
          <header className="profile-header px-6 pt-5">
            <div className="min-w-0">
              <h1 className="text-headline font-headline text-ink-strong">
                {t("nav.profile")}
              </h1>
              <p className="font-course-display text-profile-title text-ink-strong mt-5 text-balance">
                {t("learningProfile.headline")}
              </p>
              <p className="text-body text-ink-muted max-w-reading mt-3 leading-relaxed">
                {t("learningProfile.description")}
              </p>
            </div>
            <div className="min-w-0">
              <Select
                items={options}
                value={courseId ?? null}
                onValueChange={(value) => {
                  if (value)
                    onSearchChange({
                      course: String(value),
                      concept: undefined,
                      status: undefined,
                    });
                }}
              >
                <SelectTrigger
                  className="!h-auto min-h-10 w-full rounded-sm px-3 py-2"
                  aria-label={t("learningProfile.course")}
                >
                  <BookOpen aria-hidden="true" />
                  <SelectValue
                    placeholder={t("learningProfile.chooseCourse")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {options.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {data ? (
                <ProfileMasterySummary
                  data={data}
                  selected={search.status}
                  onSelect={(status) =>
                    onSearchChange({
                      status,
                      tab: "concepts",
                      concept: undefined,
                    })
                  }
                />
              ) : null}
            </div>
          </header>
          <Tabs
            value={search.tab ?? "concepts"}
            onValueChange={(value) => {
              const tab = profileTabs.find((tab) => tab === value);
              if (tab) onSearchChange({ tab });
            }}
            className="mt-5 min-w-0 gap-0"
          >
            <div className="border-border-subtle overflow-x-auto border-b px-6 pb-1">
              <TabsList
                variant="line"
                aria-label={t("learningProfile.tabs.label")}
                className="profile-tabs !h-auto justify-start gap-5"
              >
                {profileTabs.map((tab) => (
                  <TabsTrigger
                    key={tab}
                    value={tab}
                    className="text-body min-h-10 flex-none px-1 py-2"
                  >
                    {t(`learningProfile.tabs.${tab}`)}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            <div className="px-6 py-5">
              {example ? (
                <Alert className="mb-5">
                  <AlertDescription>
                    {t("learningProfile.example.notice")}
                  </AlertDescription>
                </Alert>
              ) : null}
              <TabsContent value="memory" keepMounted className="min-w-0">
                <LearnerMemorySection />
                <Link
                  to="/settings"
                  search={{ section: "profile" }}
                  className="text-body text-ink-muted mt-6 inline-flex items-center gap-2 underline underline-offset-4"
                >
                  <SlidersHorizontal className="size-4" aria-hidden="true" />
                  {t("learningProfile.profileSettings")}
                </Link>
              </TabsContent>
              {(["concepts", "history", "goals"] as const).map((tab) => (
                <TabsContent
                  key={tab}
                  value={tab}
                  keepMounted
                  className="min-w-0"
                >
                  {(!example && courses.isPending) ||
                  (courseId && !example && mastery.isPending) ? (
                    <p role="status" className="text-body text-ink-muted py-10">
                      {t("learningProfile.loading")}
                    </p>
                  ) : !example && (courses.isError || mastery.isError) ? (
                    <div role="alert" className="py-8">
                      <p className="text-body text-destructive">
                        {t("learningProfile.error")}
                      </p>
                      <Button
                        variant="outline"
                        className="mt-3"
                        onClick={() =>
                          void (courses.isError
                            ? courses.refetch()
                            : mastery.refetch())
                        }
                      >
                        {t("learningProfile.retry")}
                      </Button>
                    </div>
                  ) : !courseId ? (
                    <div className="py-10">
                      <p className="text-body text-ink-muted">
                        {t(
                          search.course
                            ? "learningProfile.courseMissing"
                            : "learningProfile.empty",
                        )}
                      </p>
                      <Button
                        variant="outline"
                        className="mt-4"
                        onClick={() =>
                          onSearchChange({ course: EXAMPLE_COURSE })
                        }
                      >
                        {t("learningProfile.example.open")}
                      </Button>
                    </div>
                  ) : tab === "goals" ? (
                    example ? (
                      <div className="border-border-subtle rounded-md border p-6">
                        <h2 className="text-profile-section font-section">
                          {t("learningProfile.example.goal")}
                        </h2>
                        <p className="text-body text-ink-muted mt-3">
                          {t("learningProfile.example.goalHint")}
                        </p>
                      </div>
                    ) : (
                      <LearningPlanTab courseId={courseId} />
                    )
                  ) : data ? (
                    tab === "history" ? (
                      <ProfileTimeline
                        concepts={data.concepts}
                        selectedId={search.concept}
                        expanded
                        onSelect={(concept) =>
                          onSearchChange({
                            concept,
                            tab: "concepts",
                            status: undefined,
                          })
                        }
                      />
                    ) : (
                      <>
                        <ProfileTimeline
                          concepts={data.concepts}
                          selectedId={
                            search.concept ?? data.concepts[0]?.concept_id
                          }
                          onSelect={(concept) =>
                            onSearchChange({ concept, status: undefined })
                          }
                          onExpand={() => onSearchChange({ tab: "history" })}
                        />
                        <ProfileConceptWorkspace
                          key={courseId}
                          courseId={courseId}
                          data={data}
                          search={search}
                          onSearchChange={onSearchChange}
                          example={example}
                        />
                      </>
                    )
                  ) : null}
                </TabsContent>
              ))}
            </div>
          </Tabs>
        </div>
      </div>
      <footer className="profile-footer bg-paper/95 border-border-subtle text-label text-ink-muted sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3">
        <span>{t("learningProfile.footer")}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-auto p-0"
          onClick={() => onSearchChange({ tab: "memory" })}
        >
          <SlidersHorizontal aria-hidden="true" data-icon="inline-start" />
          {t("learningProfile.tabs.memory")}
        </Button>
      </footer>
    </section>
  );
}
