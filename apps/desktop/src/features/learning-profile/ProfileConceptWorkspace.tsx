import { useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  BookOpen,
  ChevronRight,
  FileText,
  GitBranch,
  Link2,
  NotebookPen,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConceptMasteryBadge } from "@/features/courses/components/ConceptMasteryBadge";
import { ConceptMasteryList } from "@/features/courses/components/ConceptMasteryList";
import { useConceptMasteryDetail } from "@/features/courses/api/queries";
import type { CourseMastery } from "@/features/courses/api/types";
import {
  masteryConfidenceLabelKeys,
  masteryPercentOf,
} from "@/features/courses/masteryStatus";
import { exampleEvidence } from "@/features/learning-profile/exampleProfile";
import { ProfileEvidence } from "@/features/learning-profile/ProfileEvidence";
import { ProfileConceptSources } from "@/features/learning-profile/ProfileConceptSources";
import type { ProfileSearch } from "@/features/learning-profile/profileSearch";

const sections = [
  { value: "detail", icon: FileText },
  { value: "sources", icon: BookOpen },
  { value: "related", icon: GitBranch },
  { value: "notes", icon: NotebookPen },
] as const;

export function ProfileConceptWorkspace({
  courseId,
  data,
  search,
  onSearchChange,
  example,
}: {
  courseId: string;
  data: CourseMastery;
  search: ProfileSearch;
  onSearchChange: (patch: Partial<ProfileSearch>) => void;
  example: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [section, setSection] = useState("detail");
  const evidenceHeading = useRef<HTMLHeadingElement>(null);
  const conceptHeading = useRef<HTMLHeadingElement>(null);
  const openEvidence = () => {
    setSection("detail");
    requestAnimationFrame(() => evidenceHeading.current?.focus());
  };
  const visible = data.concepts.filter(
    (concept) => !search.status || concept.status === search.status,
  );
  const selected =
    visible.find((concept) => concept.concept_id === search.concept) ??
    visible[0];
  const detail = useConceptMasteryDetail(
    courseId,
    !example ? (selected?.concept_id ?? null) : null,
  );
  const snapshot = detail.data?.snapshot ?? selected;
  const evidence = example
    ? selected?.evidence_count
      ? exampleEvidence()
      : []
    : detail.data?.evidences;
  const items = visible.map((concept) => ({
    value: concept.concept_id,
    label: concept.canonical_name,
  }));
  return (
    <section
      className="border-border-subtle mt-6 overflow-hidden rounded-md border"
      aria-label={t("learningProfile.workspace.title")}
    >
      <h2 className="sr-only">{t("learningProfile.workspace.title")}</h2>
      {selected && snapshot ? (
        <Tabs
          value={section}
          orientation="vertical"
          onValueChange={(value) => {
            if (typeof value === "string") setSection(value);
          }}
          className="profile-concept-layout !grid gap-0"
        >
          <div className="profile-concept-sidebar min-w-0">
            <div className="p-2">
              <Select
                items={items}
                value={selected.concept_id}
                onValueChange={(value) => {
                  if (value) onSearchChange({ concept: String(value) });
                }}
              >
                <SelectTrigger
                  className="w-full"
                  aria-label={t("learningProfile.workspace.select")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {items.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {search.status ? (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-label mt-2 h-auto w-full whitespace-normal"
                  onClick={() => onSearchChange({ status: undefined })}
                >
                  {t("learningProfile.workspace.clear")}
                </Button>
              ) : null}
            </div>
            <TabsList
              variant="line"
              aria-label={t("learningProfile.workspace.navigation")}
              className="profile-concept-nav !h-auto w-full items-stretch justify-start gap-1 self-stretch p-2"
            >
              {sections.map(({ value, icon: Icon }) => (
                <TabsTrigger
                  key={value}
                  value={value}
                  className="text-body-dense data-active:bg-surface-subtle !h-auto min-h-11 flex-none justify-start gap-2 rounded-sm px-3 py-2 after:hidden"
                >
                  <Icon aria-hidden="true" />
                  {t(`learningProfile.workspace.${value}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="min-w-0 p-5">
            <div className="profile-detail-header">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3">
                  <h3
                    ref={conceptHeading}
                    tabIndex={-1}
                    className="font-course-display text-profile-title text-ink-strong break-words"
                  >
                    {snapshot.canonical_name}
                  </h3>
                  <ConceptMasteryBadge status={snapshot.status} />
                </div>
                <p className="text-body text-ink-muted max-w-reading mt-3 leading-relaxed break-words">
                  {snapshot.description}
                </p>
              </div>
              <div className="flex min-w-0 flex-col gap-2">
                {example ? (
                  <Button className="min-h-10" onClick={openEvidence}>
                    {t("learningProfile.example.verify")}
                    <ChevronRight data-icon="inline-end" aria-hidden="true" />
                  </Button>
                ) : (
                  <Link
                    className={buttonVariants({
                      className: "min-h-10 text-center whitespace-normal",
                    })}
                    to="/spaces/$courseId"
                    params={{ courseId }}
                    search={{ tab: "tests" }}
                  >
                    {t("learningProfile.workspace.verify")}
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </Link>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={openEvidence}>
                    <FileText data-icon="inline-start" aria-hidden="true" />
                    {t("learningProfile.workspace.evidence")}
                  </Button>
                  {!example ? (
                    <Link
                      to="/spaces/$courseId"
                      params={{ courseId }}
                      search={{ tab: "map" }}
                      className={buttonVariants({
                        variant: "outline",
                        size: "sm",
                      })}
                    >
                      <Link2 className="size-4" aria-hidden="true" />
                      {t("learningProfile.workspace.locate")}
                    </Link>
                  ) : null}
                </div>
              </div>
            </div>
            <TabsContent value="detail" className="min-w-0">
              <dl className="border-border-subtle text-label mt-5 flex flex-wrap gap-x-6 gap-y-3 border-t pt-4">
                <div>
                  <dt className="text-ink-muted">
                    {t("learningProfile.workspace.score")}
                  </dt>
                  <dd className="text-body font-section mt-1 tabular-nums">
                    {masteryPercentOf(snapshot.mastery_score) === null
                      ? "—"
                      : `${masteryPercentOf(snapshot.mastery_score)}%`}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">
                    {t("spaces.courseDetail.gps.detail.confidenceLabel")}
                  </dt>
                  <dd className="text-body mt-1">
                    {snapshot.confidence
                      ? t(masteryConfidenceLabelKeys[snapshot.confidence])
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">
                    {t("spaces.courseDetail.gps.detail.evidenceCountLabel")}
                  </dt>
                  <dd className="text-body mt-1 tabular-nums">
                    {snapshot.evidence_count}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">
                    {t("spaces.courseDetail.gps.detail.lastVerifiedLabel")}
                  </dt>
                  <dd className="text-body mt-1">
                    {snapshot.last_verified_at
                      ? new Date(snapshot.last_verified_at).toLocaleDateString(
                          i18n.resolvedLanguage,
                        )
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">
                    {t("spaces.courseDetail.gps.detail.lastPracticedLabel")}
                  </dt>
                  <dd className="text-body mt-1">
                    {snapshot.last_practiced_at
                      ? new Date(snapshot.last_practiced_at).toLocaleDateString(
                          i18n.resolvedLanguage,
                        )
                      : "—"}
                  </dd>
                </div>
              </dl>
              {!example && detail.isPending ? (
                <p role="status" className="text-body text-ink-muted py-5">
                  {t("learningProfile.loading")}
                </p>
              ) : null}
              {!example && detail.isError ? (
                <div className="mt-5" role="alert">
                  <p className="text-body text-destructive">
                    {t("learningProfile.evidence.error")}
                  </p>
                  <Button
                    variant="outline"
                    className="mt-3"
                    onClick={() => void detail.refetch()}
                  >
                    {t("learningProfile.retry")}
                  </Button>
                </div>
              ) : null}
              {evidence ? (
                <ProfileEvidence
                  courseId={courseId}
                  evidences={evidence}
                  example={example}
                  headingRef={evidenceHeading}
                />
              ) : null}
            </TabsContent>
            <TabsContent value="sources" className="min-w-0 pt-5">
              {example ? (
                <div>
                  <p className="text-body font-section">
                    {t("learningProfile.example.source")}
                  </p>
                  <p className="text-body text-ink-muted mt-2">
                    {t("learningProfile.example.sourceHint")}
                  </p>
                </div>
              ) : (
                <ProfileConceptSources
                  key={selected.concept_id}
                  courseId={courseId}
                  conceptId={selected.concept_id}
                />
              )}
            </TabsContent>
            <TabsContent value="related" className="min-w-0 pt-5">
              <p className="text-body text-ink-muted">
                {t("learningProfile.workspace.relatedHint")}
              </p>
              {!example ? (
                <Link
                  className="text-body mt-4 inline-flex items-center gap-2 underline underline-offset-4"
                  to="/spaces/$courseId"
                  params={{ courseId }}
                  search={{ tab: "map" }}
                >
                  <GitBranch className="size-4" aria-hidden="true" />
                  {t("learningProfile.workspace.openGraph")}
                </Link>
              ) : (
                <p className="text-body mt-4">
                  {t("learningProfile.example.relations")}
                </p>
              )}
            </TabsContent>
            <TabsContent value="notes" className="min-w-0 pt-5">
              <p className="text-label text-ink-muted">
                {t("learningProfile.example.notesLabel")}
              </p>
              <blockquote className="border-border-strong text-body text-ink mt-3 border-l-2 pl-4 leading-relaxed">
                {t("learningProfile.example.notes")}
              </blockquote>
            </TabsContent>
          </div>
        </Tabs>
      ) : (
        <div className="p-6">
          <p className="text-body text-ink-muted">
            {t(
              data.confirmed_concept_count
                ? "spaces.courseDetail.gps.filterEmpty"
                : "spaces.courseDetail.gps.emptyDescription",
            )}
          </p>
          {search.status ? (
            <Button
              size="sm"
              variant="ghost"
              className="mt-3"
              onClick={() => onSearchChange({ status: undefined })}
            >
              {t("learningProfile.workspace.clear")}
            </Button>
          ) : null}
        </div>
      )}
      {visible.length ? (
        <details className="border-border-subtle border-t px-5 py-3">
          <summary className="text-label text-ink-muted cursor-pointer py-1">
            {t("learningProfile.workspace.all", { count: visible.length })}
          </summary>
          <ConceptMasteryList
            concepts={visible}
            onSelect={(concept) => {
              onSearchChange({ concept: concept.concept_id });
              setSection("detail");
              requestAnimationFrame(() => conceptHeading.current?.focus());
            }}
          />
        </details>
      ) : null}
    </section>
  );
}
