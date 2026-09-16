import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { appToast } from "@/components/common/appToastManager";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import {
  BRAIN_PAGE_LIMIT,
  useApplyReview,
  useConceptSources,
  useCourseBrainConcepts,
} from "@/features/courses/api/courseBrain";
import type {
  BrainApplyReviewRequest,
  BrainConcept,
} from "@/features/courses/api/types";
import { cn } from "@/lib/utils";

type ReviewDecision = BrainApplyReviewRequest["decisions"][number];

type ExpandedAction = { id: string; action: "preview" | "rename" | "merge" };

type CourseBrainReviewDrawerProps = {
  courseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 有候选被处理后回调（父组件据此清空可能已失效的详情选中）。 */
  onReviewed?: () => void;
};

/**
 * 候选审核抽屉：AI 抽取概念候选的确认 / 重命名确认 / 合并 / 忽略与批量操作。
 * 单条 = 单决策请求，批量 = 勾选项合成一次 apply-review（后端单事务原子应用）。
 */
export function CourseBrainReviewDrawer({
  courseId,
  open,
  onOpenChange,
  onReviewed,
}: CourseBrainReviewDrawerProps) {
  const { t } = useTranslation();
  const candidates = useCourseBrainConcepts(courseId, {
    status: "CANDIDATE",
    limit: BRAIN_PAGE_LIMIT,
  });
  // 合并目标候选（CONFIRMED），与概念列表视图同一查询惯例（map Tab 挂载期间拉取）。
  const confirmed = useCourseBrainConcepts(courseId, {
    status: "CONFIRMED",
    limit: BRAIN_PAGE_LIMIT,
  });
  const applyReview = useApplyReview(courseId);
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [expanded, setExpanded] = useState<ExpandedAction | null>(null);

  function submit(decisions: ReviewDecision[]) {
    applyReview.mutate(
      { decisions },
      {
        onSuccess: () => {
          appToast.add({
            description: t("spaces.courseDetail.brain.review.applied", {
              count: decisions.length,
            }),
          });
          setChecked(new Set());
          setExpanded(null);
          onReviewed?.();
        },
      },
    );
  }

  function toggleChecked(id: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const items = candidates.data ?? [];
  const allChecked = items.length > 0 && checked.size === items.length;
  const pending = applyReview.isPending;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{t("spaces.courseDetail.brain.review.title")}</SheetTitle>
          <SheetDescription>
            {t("spaces.courseDetail.brain.review.drawerDescription")}
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="flex flex-col gap-3">
          {applyReview.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{applyReview.error.message}</AlertDescription>
            </Alert>
          ) : null}

          {candidates.isPending ? (
            <p
              role="status"
              className="text-body text-muted-foreground flex items-center gap-2 py-6"
            >
              <Spinner aria-hidden="true" />
              {t("spaces.courseDetail.brain.review.loadingCandidates")}
            </p>
          ) : candidates.isError ? (
            <p role="alert" className="text-body text-destructive py-6">
              {candidates.error.message}
            </p>
          ) : items.length === 0 ? (
            <p className="text-body text-muted-foreground py-6">
              {t("spaces.courseDetail.brain.review.empty")}
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3">
                <label className="text-label text-ink-muted flex min-w-0 items-center gap-2">
                  <Checkbox
                    checked={allChecked}
                    onCheckedChange={(next) =>
                      setChecked(
                        next === true
                          ? new Set(items.map((c) => c.id))
                          : new Set(),
                      )
                    }
                    aria-label={t("spaces.courseDetail.brain.review.selectAll")}
                  />
                  {t("spaces.courseDetail.brain.review.checkedCount", {
                    count: checked.size,
                  })}
                </label>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    size="sm"
                    disabled={pending || checked.size === 0}
                    onClick={() =>
                      submit(
                        [...checked].map((conceptId) => ({
                          decision_type: "confirm" as const,
                          concept_id: conceptId,
                        })),
                      )
                    }
                  >
                    {t("spaces.courseDetail.brain.review.batchConfirm", {
                      count: checked.size,
                    })}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={pending || checked.size === 0}
                    onClick={() =>
                      submit(
                        [...checked].map((conceptId) => ({
                          decision_type: "dismiss" as const,
                          concept_id: conceptId,
                        })),
                      )
                    }
                  >
                    {t("spaces.courseDetail.brain.review.batchDismiss", {
                      count: checked.size,
                    })}
                  </Button>
                </div>
              </div>

              <ul className="border-border-subtle divide-border-subtle flex min-w-0 flex-col divide-y">
                {items.map((concept) => (
                  <CandidateRow
                    key={concept.id}
                    courseId={courseId}
                    concept={concept}
                    checked={checked.has(concept.id)}
                    onToggleChecked={() => toggleChecked(concept.id)}
                    expanded={
                      expanded?.id === concept.id ? expanded.action : null
                    }
                    onToggleExpand={() =>
                      setExpanded((prev) =>
                        prev?.id === concept.id
                          ? null
                          : { id: concept.id, action: "preview" },
                      )
                    }
                    onOpenAction={(action) =>
                      setExpanded({ id: concept.id, action })
                    }
                    onCloseAction={() => setExpanded(null)}
                    confirmedTargets={confirmed.data ?? []}
                    pending={pending}
                    onSubmit={submit}
                  />
                ))}
              </ul>
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

type CandidateRowProps = {
  courseId: string;
  concept: BrainConcept;
  checked: boolean;
  onToggleChecked: () => void;
  expanded: "preview" | "rename" | "merge" | null;
  onToggleExpand: () => void;
  onOpenAction: (action: "rename" | "merge") => void;
  onCloseAction: () => void;
  confirmedTargets: BrainConcept[];
  pending: boolean;
  onSubmit: (decisions: ReviewDecision[]) => void;
};

/** 候选行：勾选 + 概要（名称/抽取描述/合并建议徽章）+ 单条操作；展开区承载来源预览与重命名/合并表单。 */
function CandidateRow({
  courseId,
  concept,
  checked,
  onToggleChecked,
  expanded,
  onToggleExpand,
  onOpenAction,
  onCloseAction,
  confirmedTargets,
  pending,
  onSubmit,
}: CandidateRowProps) {
  const { t } = useTranslation();
  const sources = useConceptSources(
    courseId,
    expanded !== null ? concept.id : null,
  );

  return (
    <li className="py-2">
      <div className="flex min-w-0 items-start gap-2">
        <Checkbox
          checked={checked}
          onCheckedChange={() => onToggleChecked()}
          aria-label={t("spaces.courseDetail.brain.review.selectOne", {
            name: concept.canonical_name,
          })}
          className="mt-1.5"
        />
        <button
          type="button"
          onClick={onToggleExpand}
          aria-expanded={expanded !== null}
          className={cn(
            "min-w-0 flex-1 cursor-pointer rounded-sm px-1 py-0.5 text-left",
            expanded === null && "hover:bg-surface-subtle",
          )}
        >
          <span className="text-body text-ink flex min-w-0 items-center gap-2">
            <span className="min-w-0 truncate font-medium">
              {concept.canonical_name}
            </span>
            {concept.suggested_target_name ? (
              <StatusTag tone="warning" className="shrink-0">
                {t("spaces.courseDetail.brain.review.mergeSuggested")}
              </StatusTag>
            ) : null}
          </span>
          {concept.description ? (
            <span className="text-label text-ink-muted mt-0.5 line-clamp-2 block">
              {concept.description}
            </span>
          ) : null}
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() =>
              onSubmit([{ decision_type: "confirm", concept_id: concept.id }])
            }
          >
            {t("spaces.courseDetail.brain.review.confirm")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={pending}
            onClick={() =>
              onSubmit([{ decision_type: "dismiss", concept_id: concept.id }])
            }
          >
            {t("spaces.courseDetail.brain.review.dismiss")}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={pending}
                  aria-label={t(
                    "spaces.courseDetail.brain.review.moreActions",
                    {
                      name: concept.canonical_name,
                    },
                  )}
                />
              }
            >
              <MoreHorizontal aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-44">
              <DropdownMenuItem onClick={() => onOpenAction("rename")}>
                {t("spaces.courseDetail.brain.review.renameConfirm")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenAction("merge")}>
                {t("spaces.courseDetail.brain.review.mergeInto")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {expanded !== null ? (
        <div className="border-border-subtle mt-2 ml-6 flex flex-col gap-3 border-l pl-3">
          {expanded === "rename" ? (
            <RenameForm
              concept={concept}
              pending={pending}
              onClose={onCloseAction}
              onSubmit={onSubmit}
            />
          ) : null}
          {expanded === "merge" ? (
            <MergeForm
              concept={concept}
              confirmedTargets={confirmedTargets}
              pending={pending}
              onClose={onCloseAction}
              onSubmit={onSubmit}
            />
          ) : null}
          <SourcePreview
            concept={concept}
            quotes={(sources.data?.anchors ?? [])
              .map((anchor) => anchor.quote?.trim() ?? "")
              .filter(Boolean)
              .slice(0, 3)}
            loading={sources.isPending}
          />
        </div>
      ) : null}
    </li>
  );
}

type RenameFormProps = {
  concept: BrainConcept;
  pending: boolean;
  onClose: () => void;
  onSubmit: (decisions: ReviewDecision[]) => void;
};

/** 重命名后确认表单：展开时挂载，以候选规范名为初值，收起即销毁重置。 */
function RenameForm({ concept, pending, onClose, onSubmit }: RenameFormProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(concept.canonical_name);
  const valid = name.trim().length > 0 && name.length <= 100;

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onSubmit([
          {
            decision_type: "confirm",
            concept_id: concept.id,
            new_name: name.trim(),
          },
        ]);
      }}
    >
      <Field>
        <FieldLabel htmlFor={`rename-${concept.id}`}>
          {t("spaces.courseDetail.brain.review.renameLabel")}
        </FieldLabel>
        <Input
          id={`rename-${concept.id}`}
          value={name}
          maxLength={100}
          onChange={(event) => setName(event.target.value)}
          autoComplete="off"
        />
      </Field>
      <Button type="submit" size="sm" disabled={pending || !valid}>
        {pending ? (
          <Spinner aria-hidden="true" data-icon="inline-start" />
        ) : null}
        {t("spaces.courseDetail.brain.review.renameSubmit")}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={pending}
        onClick={onClose}
      >
        {t("spaces.courseDetail.brain.review.cancel")}
      </Button>
    </form>
  );
}

type MergeFormProps = {
  concept: BrainConcept;
  confirmedTargets: BrainConcept[];
  pending: boolean;
  onClose: () => void;
  onSubmit: (decisions: ReviewDecision[]) => void;
};

/** 合并表单：默认预填确定性合并建议目标；展开时挂载，收起即销毁重置。 */
function MergeForm({
  concept,
  confirmedTargets,
  pending,
  onClose,
  onSubmit,
}: MergeFormProps) {
  const { t } = useTranslation();
  const [targetId, setTargetId] = useState(concept.suggested_target_id ?? "");
  const targetItems = confirmedTargets.map((target) => ({
    value: target.id,
    label: target.canonical_name,
  }));

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!targetId) return;
        onSubmit([
          {
            decision_type: "merge",
            concept_id: concept.id,
            target_concept_id: targetId,
          },
        ]);
      }}
    >
      <Field className="min-w-0 flex-1">
        <FieldLabel htmlFor={`merge-${concept.id}`}>
          {t("spaces.courseDetail.brain.review.mergeTargetLabel")}
        </FieldLabel>
        <Select
          items={targetItems}
          value={targetId || null}
          onValueChange={(value) => setTargetId((value as string) ?? "")}
        >
          <SelectTrigger id={`merge-${concept.id}`} className="w-full">
            <SelectValue
              placeholder={t(
                "spaces.courseDetail.brain.review.mergeTargetPlaceholder",
              )}
            >
              {confirmedTargets.find((c) => c.id === targetId)
                ?.canonical_name ?? null}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {targetItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Button type="submit" size="sm" disabled={pending || !targetId}>
        {pending ? (
          <Spinner aria-hidden="true" data-icon="inline-start" />
        ) : null}
        {t("spaces.courseDetail.brain.review.merge")}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={pending}
        onClick={onClose}
      >
        {t("spaces.courseDetail.brain.review.cancel")}
      </Button>
    </form>
  );
}

type SourcePreviewProps = {
  concept: BrainConcept;
  quotes: string[];
  loading: boolean;
};

/** 来源预览：候选的首批锚点逐字摘录（合并建议完整文案同区展示）。 */
function SourcePreview({ concept, quotes, loading }: SourcePreviewProps) {
  const { t } = useTranslation();

  return (
    <div className="min-w-0">
      {concept.suggested_target_name ? (
        <p className="text-label text-ink-muted mb-1">
          {t("spaces.courseDetail.brain.concepts.suggestedMerge", {
            name: concept.suggested_target_name,
          })}
        </p>
      ) : null}
      <p className="text-label text-ink-muted mb-1">
        {t("spaces.courseDetail.brain.sources.title")}
      </p>
      {loading ? (
        <p
          role="status"
          className="text-label text-muted-foreground flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.courseDetail.brain.review.loadingSources")}
        </p>
      ) : quotes.length === 0 ? (
        <p className="text-label text-muted-foreground">
          {t("spaces.courseDetail.brain.sources.empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {quotes.map((quote, index) => (
            <li
              key={`${concept.id}-quote-${index}`}
              className="text-label text-ink-muted line-clamp-2"
              title={quote}
            >
              {quote}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
