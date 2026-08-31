import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { quizTestKeys } from "@/features/quiz-tests/api/keys";
import { quizTestApi } from "@/features/quiz-tests/api/quizTests";
import {
  QUIZ_QUESTION_TYPES,
  asTestView,
  type QuizTestAnswer,
  type QuizTestDetail,
  type QuizTestItem,
  type TestView,
} from "@/features/quiz-tests/api/types";
import { TestQuestionCard } from "@/features/quiz-tests/components/TestQuestionCard";

const SECTION_NUMERALS = ["一", "二", "三", "四", "五"] as const;

type PaperSection = {
  type: string;
  title: string;
  shortTitle: string;
  items: QuizTestItem[];
};

function firstUnansweredIndex(items: QuizTestItem[]): number {
  const index = items.findIndex((item) => item.answered_at === null);
  return index === -1 ? 0 : index;
}

export function QuizTestPage({
  courseId,
  testId,
  shortage,
  view,
}: {
  courseId: string;
  testId: string;
  shortage?: number;
  view: TestView;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const test = useQuery({
    queryKey: quizTestKeys.detail(testId),
    queryFn: () => quizTestApi.get(testId),
    // 评分中轮询：GRADING 态每 1.5s 拉一次，其余状态停轮
    refetchInterval: (query) =>
      query.state.data?.status === "GRADING" ? 1500 : false,
  });

  const patchView = (next: TestView) => {
    void navigate({
      to: "/spaces/$courseId/tests/$testId",
      params: { courseId, testId },
      search: { view: next, ...(shortage ? { shortage } : {}) },
      replace: true,
    });
  };

  if (test.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2 p-8"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.simulations.paper.loading")}
      </p>
    );
  }

  if (test.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("spaces.simulations.paper.errorTitle")}
        </h1>
        <Button
          variant="outline"
          className="mt-6"
          onClick={() => void test.refetch()}
        >
          {t("spaces.simulations.retry")}
        </Button>
      </section>
    );
  }

  return (
    <ExamPaper
      courseId={courseId}
      data={test.data}
      shortage={shortage}
      view={view}
      onViewChange={patchView}
    />
  );
}

function ExamPaper({
  courseId,
  data,
  shortage,
  view,
  onViewChange,
}: {
  courseId: string;
  data: QuizTestDetail;
  shortage?: number;
  view: TestView;
  onViewChange: (next: TestView) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const items = data.items;
  const answering = data.status === "IN_PROGRESS";
  const reviewing =
    data.status === "COMPLETED" || data.status === "GRADING_FAILED";

  /* 离开作答态（交卷 / 放弃）即同步课程页列表（列表缓存默认 60s 不自动刷新） */
  useEffect(() => {
    if (data.status !== "IN_PROGRESS") {
      void queryClient.invalidateQueries({
        queryKey: quizTestKeys.list(data.course_id),
      });
    }
  }, [data.status, data.course_id, queryClient]);

  const answer = useMutation({
    mutationFn: ({
      itemId,
      answer: value,
    }: {
      itemId: string;
      answer: QuizTestAnswer;
    }) => quizTestApi.answer(data.id, { item_id: itemId, answer: value }),
    onSuccess: (result) =>
      queryClient.setQueryData(quizTestKeys.detail(data.id), result),
    onError: () =>
      queryClient.invalidateQueries({ queryKey: quizTestKeys.detail(data.id) }),
  });
  const submit = useMutation({
    mutationFn: () => quizTestApi.submit(data.id),
    onSuccess: (result) => {
      queryClient.setQueryData(quizTestKeys.detail(data.id), result);
      void queryClient.invalidateQueries({
        queryKey: quizTestKeys.list(data.course_id),
      });
    },
  });
  const regrade = useMutation({
    mutationFn: () => quizTestApi.regrade(data.id),
    onSuccess: (result) =>
      queryClient.setQueryData(quizTestKeys.detail(data.id), result),
  });
  const abandon = useMutation({
    mutationFn: () => quizTestApi.abandon(data.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: quizTestKeys.detail(data.id),
      });
      await queryClient.invalidateQueries({
        queryKey: quizTestKeys.list(courseId),
      });
      void navigate({
        to: "/spaces/$courseId",
        params: { courseId },
        search: { tab: "tests" },
      });
    },
  });

  const sections = useMemo<PaperSection[]>(
    () => buildSections(items, t),
    [items, t],
  );
  const [activeIndex, setActiveIndex] = useState(() =>
    firstUnansweredIndex(items),
  );
  const [activeSection, setActiveSection] = useState(() =>
    firstUnansweredSection(sections, items),
  );
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);

  const answeredCount = data.answered_count;
  const answeredAll = items.length > 0 && answeredCount === items.length;
  const pendingItemId =
    answer.isPending && answer.variables ? answer.variables.itemId : null;

  /* 单题模式：键盘 ←→ 翻题（输入框聚焦时不拦截） */
  useEffect(() => {
    if (view !== "single") return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.key === "ArrowLeft") {
        setActiveIndex((current) => Math.max(0, current - 1));
      }
      if (event.key === "ArrowRight") {
        setActiveIndex((current) => Math.min(items.length - 1, current + 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, items.length]);

  const sectionIndexFor = (item: QuizTestItem) => {
    const index = sections.findIndex((section) =>
      section.items.some((entry) => entry.id === item.id),
    );
    return index === -1 ? 0 : index;
  };

  const jumpToItem = (item: QuizTestItem, index: number) => {
    if (view === "single") {
      setActiveIndex(index);
      return;
    }
    if (view === "sectioned") {
      setActiveSection(sectionIndexFor(item));
      return;
    }
    document
      .getElementById(`test-item-${item.id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  /* 交卷确认后触发评分；无简答题时后端同步落 COMPLETED */
  const submitButton = (className?: string) => (
    <Button
      className={className}
      disabled={!answeredAll}
      onClick={() => setConfirmSubmit(true)}
    >
      {t("spaces.simulations.paper.submitButton")}
    </Button>
  );

  const renderCard = (item: QuizTestItem) => (
    <TestQuestionCard
      key={item.id}
      item={item}
      locked={!answering}
      pending={pendingItemId === item.id}
      reviewing={reviewing}
      onSubmit={(itemId, value) => answer.mutate({ itemId, answer: value })}
    />
  );

  const currentSection = sections[Math.min(activeSection, sections.length - 1)];

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto py-8">
      <Link
        to="/spaces/$courseId"
        params={{ courseId }}
        search={{ tab: "tests" }}
        className="text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex w-fit items-center gap-1.5 rounded-sm focus-visible:ring-3"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t("spaces.simulations.paper.back")}
      </Link>

      {!answering ? (
        <p
          role="status"
          className="bg-surface-subtle text-body text-muted-foreground mt-5 flex items-center gap-2 px-3 py-2"
        >
          {data.status === "GRADING" ? <Spinner aria-hidden="true" /> : null}
          {t(`spaces.simulations.paper.banner.${data.status}`)}
        </p>
      ) : null}
      {shortage ? (
        <p
          role="status"
          className="bg-warning-soft text-warning-foreground text-body mt-4 px-3 py-2"
        >
          {t("spaces.simulations.paper.shortage", { count: shortage })}
        </p>
      ) : null}

      <div className="mt-5 flex gap-10">
        {answering ? (
          <aside className="sticky top-6 w-56 shrink-0 self-start">
            {" "}
            <p className="text-section font-section text-ink">
              {t("spaces.simulations.paper.answerCard")}
            </p>
            <p className="text-label text-muted-foreground mt-1 tabular-nums">
              {t("spaces.simulations.paper.progress", {
                answered: answeredCount,
                total: items.length,
              })}
            </p>
            <div className="bg-surface-subtle mt-3 h-1 w-full">
              <div
                className="bg-ink-strong h-full transition-all"
                style={{ width: `${(answeredCount / items.length) * 100}%` }}
              />
            </div>
            <div className="mt-4 grid grid-cols-5 gap-1.5">
              {items.map((item, index) => {
                const answered = item.answered_at !== null;
                const isCurrent = view === "single" && index === activeIndex;
                const inCurrentSection =
                  view === "sectioned" &&
                  sectionIndexFor(item) === activeSection;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-label={t("spaces.simulations.paper.jumpTo", {
                      index: item.sequence_no,
                      type: t(`record.detail.quiz.type.${item.question_type}`),
                    })}
                    className={`text-label h-9 rounded-xs tabular-nums transition-colors ${
                      isCurrent
                        ? "bg-learning text-primary-foreground"
                        : inCurrentSection
                          ? "bg-learning-soft text-learning-foreground"
                          : answered
                            ? "bg-ink-strong text-paper"
                            : "bg-surface-subtle text-muted-foreground hover:bg-surface-strong"
                    }`}
                    onClick={() => jumpToItem(item, index)}
                  >
                    {item.sequence_no}
                  </button>
                );
              })}
            </div>
            {submitButton("mt-5 w-full disabled:cursor-not-allowed")}
            {!answeredAll ? (
              <p className="text-label text-muted-foreground mt-2">
                {t("spaces.simulations.paper.allAnswered")}
              </p>
            ) : null}
            <Button
              variant="ghost"
              className="text-muted-foreground mt-2 w-full"
              onClick={() => setConfirmAbandon(true)}
            >
              {t("spaces.simulations.paper.abandonButton")}
            </Button>
          </aside>
        ) : reviewing ? (
          <ResultSummary
            data={data}
            regradePending={regrade.isPending}
            regradeError={regrade.isError ? regrade.error.message : null}
            onRegrade={() => regrade.mutate()}
            onRetake={() =>
              void navigate({
                to: "/spaces/$courseId",
                params: { courseId },
                search: { tab: "tests" },
              })
            }
          />
        ) : null}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-headline font-headline text-ink-strong">
                {t("spaces.simulations.paper.title")}
              </h1>
              <p className="text-label text-muted-foreground mt-1.5">
                {t("spaces.simulations.paper.description", {
                  count: items.length,
                })}
              </p>
            </div>
            <Tabs
              value={view}
              onValueChange={(next) => onViewChange(asTestView(next))}
              aria-label={t("spaces.simulations.paper.viewLabel")}
            >
              <TabsList>
                <TabsTrigger value="single">
                  {t("spaces.simulations.paper.viewSingle")}
                </TabsTrigger>
                <TabsTrigger value="sectioned">
                  {t("spaces.simulations.paper.viewSectioned")}
                </TabsTrigger>
                <TabsTrigger value="full">
                  {t("spaces.simulations.paper.viewFull")}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {view === "single" ? (
            <div className="mt-6">
              <p className="text-label text-muted-foreground tabular-nums">
                {t("spaces.simulations.paper.position", {
                  section:
                    sections[sectionIndexFor(items[activeIndex])]?.shortTitle ??
                    "",
                  index: activeIndex + 1,
                  total: items.length,
                })}
                {answering ? (
                  <span className="ml-1">
                    {t("spaces.simulations.paper.keyboardHint")}
                  </span>
                ) : null}
              </p>
              <div className="border-border mt-4 border-t pt-2">
                {renderCard(items[activeIndex])}
              </div>
              <div className="mt-5 flex items-center justify-between">
                <Button
                  variant="ghost"
                  className="disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={activeIndex === 0}
                  onClick={() =>
                    setActiveIndex((current) => Math.max(0, current - 1))
                  }
                >
                  <ChevronLeft className="size-4" />
                  {t("spaces.simulations.paper.prev")}
                </Button>
                {activeIndex < items.length - 1 ? (
                  <Button
                    variant="outline"
                    onClick={() =>
                      setActiveIndex((current) =>
                        Math.min(items.length - 1, current + 1),
                      )
                    }
                  >
                    {t("spaces.simulations.paper.next")}
                    <ChevronRight className="size-4" />
                  </Button>
                ) : answering ? (
                  submitButton("disabled:cursor-not-allowed")
                ) : null}
              </div>
            </div>
          ) : null}

          {view === "sectioned" ? (
            <div className="mt-6">
              <div className="flex items-center gap-2">
                {sections.map((section, index) => {
                  const active = index === activeSection;
                  const done =
                    answering &&
                    section.items.every((item) => item.answered_at !== null);
                  return (
                    <div
                      key={section.type}
                      className="flex flex-1 items-center gap-2 last:flex-none"
                    >
                      <button
                        type="button"
                        className={`text-label flex items-center gap-2 rounded-xs px-2 py-1.5 transition-colors ${
                          active
                            ? "bg-learning-soft text-learning-foreground"
                            : "text-muted-foreground hover:bg-surface-subtle"
                        }`}
                        onClick={() => setActiveSection(index)}
                      >
                        {done ? (
                          <span className="bg-success-foreground text-paper flex size-4 items-center justify-center rounded-full">
                            <Check className="size-2.5" />
                          </span>
                        ) : (
                          <span
                            className={`size-2.5 rounded-full ${active ? "bg-learning" : "bg-surface-strong"}`}
                          />
                        )}
                        {section.shortTitle}
                      </button>
                      {index < sections.length - 1 ? (
                        <div className="bg-surface-strong h-px flex-1" />
                      ) : null}
                    </div>
                  );
                })}
              </div>
              <div className="border-border mt-6 border-t pt-2">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-section font-section text-ink">
                    {currentSection.title}
                  </h2>
                  {answering ? (
                    <p className="text-label text-muted-foreground tabular-nums">
                      {t("spaces.simulations.paper.sectionProgress", {
                        answered: currentSection.items.filter(
                          (item) => item.answered_at !== null,
                        ).length,
                        total: currentSection.items.length,
                      })}
                    </p>
                  ) : null}
                </div>
                <ul className="mt-2">
                  {currentSection.items.map((item) => (
                    <li key={item.id}>{renderCard(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="mt-5 flex items-center justify-between">
                <Button
                  variant="ghost"
                  className="disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={activeSection === 0}
                  onClick={() =>
                    setActiveSection((current) => Math.max(0, current - 1))
                  }
                >
                  {t("spaces.simulations.paper.prevSection")}
                </Button>
                {activeSection < sections.length - 1 ? (
                  <Button
                    variant="outline"
                    onClick={() =>
                      setActiveSection((current) =>
                        Math.min(sections.length - 1, current + 1),
                      )
                    }
                  >
                    {t("spaces.simulations.paper.nextSection")}
                  </Button>
                ) : answering ? (
                  submitButton("disabled:cursor-not-allowed")
                ) : null}
              </div>
            </div>
          ) : null}

          {view === "full" ? (
            <div className="mt-6">
              <div className="border-border border-b pb-6 text-center">
                <p className="text-headline font-headline text-ink-strong">
                  {t("spaces.simulations.paper.title")}
                </p>
                <p className="text-label text-muted-foreground mt-2 tabular-nums">
                  {t("spaces.simulations.paper.description", {
                    count: items.length,
                  })}
                </p>
              </div>
              {sections.map((section) => (
                <div key={section.type} className="mt-8">
                  <h2 className="text-section font-section text-ink">
                    {section.title}
                  </h2>
                  <ul className="mt-2">
                    {section.items.map((item) => (
                      <li key={item.id} id={`test-item-${item.id}`}>
                        {renderCard(item)}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <Dialog open={confirmAbandon} onOpenChange={setConfirmAbandon}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("spaces.simulations.paper.abandonDialog.title")}
            </DialogTitle>
            <DialogDescription>
              {t("spaces.simulations.paper.abandonDialog.description")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={abandon.isPending}
              onClick={() => setConfirmAbandon(false)}
            >
              {t("spaces.simulations.paper.abandonDialog.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={abandon.isPending}
              onClick={() => abandon.mutate()}
            >
              {abandon.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("spaces.simulations.paper.abandonDialog.confirm")}
            </Button>
          </DialogFooter>
          {abandon.isError ? (
            <p role="alert" className="text-body text-destructive">
              {abandon.error.message}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={confirmSubmit} onOpenChange={setConfirmSubmit}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("spaces.simulations.paper.submitDialog.title")}
            </DialogTitle>
            <DialogDescription>
              {t("spaces.simulations.paper.submitDialog.description", {
                total: items.length,
                answered: answeredCount,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={submit.isPending}
              onClick={() => setConfirmSubmit(false)}
            >
              {t("spaces.simulations.paper.submitDialog.cancel")}
            </Button>
            <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
              {submit.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("spaces.simulations.paper.submitDialog.confirm")}
            </Button>
          </DialogFooter>
          {submit.isError ? (
            <p role="alert" className="text-body text-destructive">
              {submit.error.message}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

/** 终态成绩摘要侧栏：得分（×100）、对/错/半对/未计分/待复核计数、重新评分与再考一张 */
function ResultSummary({
  data,
  regradePending,
  regradeError,
  onRegrade,
  onRetake,
}: {
  data: QuizTestDetail;
  regradePending: boolean;
  regradeError: string | null;
  onRegrade: () => void;
  onRetake: () => void;
}) {
  const { t } = useTranslation();
  const counts = { correct: 0, wrong: 0, partial: 0, unscored: 0, review: 0 };
  for (const item of data.items) {
    if (item.result === "CORRECT") counts.correct += 1;
    else if (item.result === "WRONG") counts.wrong += 1;
    else if (item.result === "PARTIAL") counts.partial += 1;
    else counts.unscored += 1;
    if (item.ai_grade?.needs_review) counts.review += 1;
  }
  const counted = counts.correct + counts.wrong + counts.partial;
  return (
    <aside className="sticky top-6 w-56 shrink-0 self-start">
      <p className="text-label text-muted-foreground">
        {t("spaces.simulations.paper.result.scoreLabel")}
      </p>
      <p className="text-headline font-headline text-ink-strong mt-1 tabular-nums">
        {data.score != null ? Math.round(data.score * 100) : "—"}
        <span className="text-body text-muted-foreground">
          {" "}
          {t("spaces.simulations.paper.result.scoreSuffix")}
        </span>
      </p>
      <Separator className="my-4" />
      <div className="space-y-2">
        <p className="text-label text-muted-foreground tabular-nums">
          {t("spaces.simulations.paper.result.counts", {
            correct: counts.correct,
            wrong: counts.wrong,
            partial: counts.partial,
          })}
        </p>
        {counts.unscored > 0 ? (
          <p className="text-label text-muted-foreground tabular-nums">
            {t("spaces.simulations.paper.result.unscored", {
              unscored: counts.unscored,
              counted,
            })}
          </p>
        ) : null}
        {counts.review > 0 ? (
          <p className="text-label text-warning-foreground tabular-nums">
            {t("spaces.simulations.paper.result.reviewCount", {
              count: counts.review,
            })}
          </p>
        ) : null}
      </div>
      {data.status === "GRADING_FAILED" ? (
        <Button
          variant="outline"
          className="mt-5 w-full"
          disabled={regradePending}
          onClick={onRegrade}
        >
          {regradePending ? <Spinner aria-hidden="true" /> : null}
          {t("spaces.simulations.paper.result.regradeButton")}
        </Button>
      ) : null}
      {regradeError ? (
        <p role="alert" className="text-label text-destructive mt-2">
          {regradeError}
        </p>
      ) : null}
      <Button variant="outline" className="mt-2 w-full" onClick={onRetake}>
        {t("spaces.simulations.paper.result.retakeButton")}
      </Button>
    </aside>
  );
}

function buildSections(
  items: QuizTestItem[],
  t: (key: string, options?: Record<string, unknown>) => string,
): PaperSection[] {
  const presentTypes = QUIZ_QUESTION_TYPES.filter((type) =>
    items.some((item) => item.question_type === type),
  );
  return presentTypes.map((type, index) => {
    const label = t(`record.detail.quiz.type.${type}`);
    return {
      type,
      title: t("spaces.simulations.paper.sectionTitle", {
        index: SECTION_NUMERALS[index],
        type: label,
      }),
      shortTitle: label,
      items: items.filter((item) => item.question_type === type),
    };
  });
}

function firstUnansweredSection(
  sections: PaperSection[],
  items: QuizTestItem[],
): number {
  if (sections.length === 0) return 0;
  const firstUnanswered = items.find((item) => item.answered_at === null);
  if (!firstUnanswered) return 0;
  const index = sections.findIndex((section) =>
    section.items.some((item) => item.id === firstUnanswered.id),
  );
  return index === -1 ? 0 : index;
}
