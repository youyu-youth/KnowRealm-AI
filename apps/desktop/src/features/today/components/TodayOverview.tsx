import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Bot, Check, Circle, FileText, Trophy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { todayKeys } from "@/features/today/api/keys";
import { todayApi } from "@/features/today/api/today";
import { TodayTodos } from "@/features/today/components/TodayTodos";
import { cn } from "@/lib/utils";

const sampleActions = [
  ["processing", "warning"],
  ["review", "neutral"],
  ["classify", "neutral"],
] as const;

const sampleAssets = ["summary", "knowledgePoint", "reviewMaterial"] as const;

export function TodayOverview() {
  const { t, i18n } = useTranslation();
  const pending = useQuery({
    queryKey: todayKeys.pendingSummaries,
    queryFn: todayApi.pendingSummaries,
  });
  const lead = pending.data?.[0];
  const date = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());

  return (
    <div className="grid gap-6">
      <header className="flex items-end justify-between gap-6">
        <div>
          <p className="text-label text-ink-muted font-label">{date}</p>
          <h1 className="text-headline font-headline text-ink-strong mt-1">
            {t("today.title")}
          </h1>
        </div>
        <p className="text-body-dense text-ink-muted data:block hidden max-w-md text-right">
          {t("today.description")}
        </p>
      </header>

      <section
        aria-labelledby="today-chain-title"
        className="bg-surface-raised border-border-subtle rounded-md border"
      >
        <div className="border-border-subtle flex items-center justify-between gap-4 border-b px-5 py-3">
          <div className="flex items-center gap-2">
            <h2
              id="today-chain-title"
              className="text-section font-section text-ink-strong"
            >
              {t("today.overview.chainTitle")}
            </h2>
            {!lead ? (
              <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
            ) : null}
          </div>
          {lead ? (
            <Link
              to="/records/$recordId"
              params={{ recordId: lead.record_id }}
              className={buttonVariants({ size: "sm" })}
            >
              {t("today.todoAction")}
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          ) : null}
        </div>
        <div className="data:grid-cols-4 grid grid-cols-1 gap-y-4 px-5 py-5">
          {["capture", "processing", "summary", "assets"].map(
            (stage, index) => {
              const activeIndex = lead
                ? 2
                : pending.isPending || pending.isError
                  ? -1
                  : 1;
              const complete = index < activeIndex;
              const active = index === activeIndex;
              return (
                <div key={stage} className="relative flex min-w-0 gap-3 pr-4">
                  {index < 3 ? (
                    <span className="bg-border-subtle data:left-6 data:h-px data:w-[calc(100%-1.5rem)] absolute top-3 left-3 h-[calc(100%+1rem)] w-px" />
                  ) : null}
                  <span
                    className={cn(
                      "border-border-strong bg-surface-raised relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border",
                      (complete || active) && "border-ink bg-ink text-paper",
                    )}
                  >
                    {complete ? (
                      <Check className="size-3.5" aria-hidden="true" />
                    ) : (
                      <Circle
                        className="size-2 fill-current"
                        aria-hidden="true"
                      />
                    )}
                  </span>
                  <div className="min-w-0 pt-0.5">
                    <p className="text-body-dense text-ink-strong font-medium">
                      {t(`today.overview.chain.${stage}`)}
                    </p>
                    <p
                      className="text-label text-ink-faint mt-1 truncate"
                      title={active && lead ? lead.title : undefined}
                    >
                      {active && lead
                        ? lead.title
                        : t(`today.overview.chain.${stage}Hint`)}
                    </p>
                  </div>
                </div>
              );
            },
          )}
        </div>
      </section>

      <div className="compact:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)] grid gap-5">
        <section
          aria-labelledby="today-actions-title"
          className="bg-surface-raised border-border-subtle min-w-0 rounded-md border p-5"
        >
          <SectionHeading
            id="today-actions-title"
            title={t("today.overview.actionsTitle")}
            to="/inbox"
            action={t("today.overview.openInbox")}
          />
          <TodayTodos
            summaries={pending.data}
            isSummariesPending={pending.isPending}
            isSummariesError={pending.isError}
            onRetrySummaries={() => void pending.refetch()}
          />
          <ul className="divide-border-subtle mt-2 divide-y">
            {sampleActions.map(([key, tone]) => (
              <li key={key} className="flex min-w-0 items-center gap-3 py-2.5">
                <span
                  className="border-border-strong size-4 shrink-0 rounded-full border"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-body-dense text-ink-strong truncate font-medium">
                    {t(`today.overview.actions.${key}.title`)}
                  </p>
                  <p className="text-label text-ink-faint mt-0.5 truncate">
                    {t(`today.overview.actions.${key}.detail`)}
                  </p>
                </div>
                <StatusTag tone={tone}>
                  {t(`today.overview.actions.${key}.status`)}
                </StatusTag>
                <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
              </li>
            ))}
          </ul>
          <Separator className="my-3" />
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-surface-subtle min-w-0 rounded-sm px-3 py-2.5">
              <p className="text-label text-ink-muted font-label">
                {t("today.overview.continueTitle")}
              </p>
              <p className="text-body-dense text-ink-strong mt-1 truncate">
                {t("today.overview.continueItem")}
              </p>
              <Link
                to="/spaces"
                className="text-label text-ink-muted hover:text-ink-strong mt-1 inline-block"
              >
                {t("today.overview.openCourses")}
              </Link>
            </div>
            <Link
              to="/chat"
              className="bg-surface-subtle hover:bg-surface-strong flex min-w-0 items-center gap-3 rounded-sm px-3 py-2.5"
            >
              <Bot className="text-ink size-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="text-body-dense text-ink-strong block font-medium">
                  {t("today.rightRail.assistantTitle")}
                </span>
                <span className="text-label text-ink-muted block truncate">
                  {t("today.rightRail.assistantDescription")}
                </span>
              </span>
              <ArrowRight
                className="text-ink-muted size-4 shrink-0"
                aria-hidden="true"
              />
            </Link>
          </div>
        </section>

        <section
          aria-labelledby="today-assets-title"
          className="bg-surface-raised border-border-subtle min-w-0 rounded-md border p-5"
        >
          <SectionHeading
            id="today-assets-title"
            title={t("today.overview.assetsTitle")}
            to="/library"
            action={t("today.overview.openLibrary")}
            sample
          />
          <ul className="divide-border-subtle mt-3 divide-y">
            {sampleAssets.map((key) => (
              <li
                key={key}
                className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3"
              >
                <FileText
                  className="text-ink-muted size-4"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-body-dense text-ink-strong truncate font-medium">
                    {t(`today.overview.assets.${key}.title`)}
                  </p>
                  <p className="text-label text-ink-faint data:block mt-0.5 hidden truncate">
                    {t(`today.overview.assets.${key}.source`)}
                  </p>
                </div>
                <StatusTag>{t(`today.overview.assets.${key}.type`)}</StatusTag>
              </li>
            ))}
          </ul>
          <Separator className="my-4" />
          <div className="flex items-center gap-3">
            <Trophy className="text-ink size-4" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-body-dense text-ink-strong font-medium">
                {t("today.rightRail.achievementTitle")}
              </p>
              <p className="text-label text-ink-muted mt-0.5 truncate">
                {t("today.overview.achievementSample")}
              </p>
            </div>
            <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          </div>
        </section>
      </div>
    </div>
  );
}

type SectionHeadingProps = {
  id: string;
  title: string;
  to: "/inbox" | "/library";
  action: string;
  sample?: boolean;
};

function SectionHeading({
  id,
  title,
  to,
  action,
  sample,
}: SectionHeadingProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-2">
        <h2 id={id} className="text-section font-section text-ink-strong">
          {title}
        </h2>
        {sample ? (
          <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
        ) : null}
      </div>
      <Link
        to={to}
        className="text-label text-ink-muted hover:text-ink-strong inline-flex items-center gap-1"
      >
        {action}
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </div>
  );
}
