import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  Award,
  BadgeCheck,
  Brain,
  Plus,
  Send,
  Target,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const focusItems = [
  ["高等数学（上）复习", "微分中值定理及其应用", "10:30"],
  ["线性代数课后习题", "完成习题 3.2.1～3.2.5", "14:00"],
  ["数据结构预习", "栈和队列", "16:30"],
  ["期末复习计划", "梳理各科薄弱环节", "20:00"],
] as const;

const achievements = [
  [Award, "深度思考者", "连续学习 7 天"],
  [Brain, "知识探索者", "本周生成 10 篇总结"],
  [BadgeCheck, "习题达人", "习题完成率达 80%"],
  [Target, "专注之星", "本周专注学习 6.5 小时"],
] as const;

export function TodayRightRail() {
  const { t } = useTranslation();

  return (
    <aside
      aria-label={t("today.rightRail.label")}
      className="grid min-w-0 gap-4"
    >
      <section className="bg-card border-border/60 rounded-lg border p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <h2 className="text-section font-section text-ink">
              {t("today.rightRail.focusTitle")}
            </h2>
            <span className="bg-surface-subtle text-muted-foreground text-label rounded-xs px-1.5 py-0.5">
              {t("today.stats.insights.sampleTag")}
            </span>
          </div>
          <Link
            to="/inbox"
            className="text-label text-muted-foreground hover:text-ink focus-visible:ring-ring inline-flex items-center gap-1 rounded-sm outline-none focus-visible:ring-2"
          >
            {t("today.rightRail.viewAll")}
            <ArrowRight aria-hidden="true" className="size-3.5" />
          </Link>
        </div>
        <ol className="mt-4 grid gap-4">
          {focusItems.map(([title, detail, time]) => (
            <li key={title} className="grid grid-cols-[auto_1fr_auto] gap-2.5">
              <span
                aria-hidden="true"
                className="border-muted-foreground/60 mt-1 size-3.5 rounded-full border"
              />
              <div className="min-w-0">
                <p className="text-body text-ink truncate font-medium">
                  {title}
                </p>
                <p className="text-label text-muted-foreground mt-0.5 truncate">
                  {detail}
                </p>
              </div>
              <time className="text-label text-muted-foreground pt-0.5 tabular-nums">
                {time}
              </time>
            </li>
          ))}
        </ol>
        <Link
          to="/inbox"
          className="text-label text-muted-foreground hover:text-ink focus-visible:ring-ring mt-4 inline-flex items-center gap-2 rounded-sm outline-none focus-visible:ring-2"
        >
          <Plus aria-hidden="true" className="size-3.5" />
          {t("today.rightRail.addTodo")}
        </Link>
      </section>

      <section className="rounded-lg bg-[#151a1d] p-4 text-[#f5f7f8]">
        <h2 className="text-section font-section flex items-center gap-2">
          {t("today.rightRail.assistantTitle")}
          <Plus aria-hidden="true" className="size-4" />
        </h2>
        <p className="mt-1 text-xs text-[#aeb8bf]">
          {t("today.rightRail.assistantDescription")}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {[
            "帮我总结今天的学习内容",
            "生成期末复习计划",
            "帮我复习薄弱知识点",
          ].map((prompt) => (
            <Link
              key={prompt}
              to="/chat"
              className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-[#dce3e7] transition-colors hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none"
            >
              {prompt}
            </Link>
          ))}
        </div>
        <Link
          to="/chat"
          className="mt-4 flex min-h-10 items-center justify-between rounded-lg border border-white/10 bg-white/7 px-3 text-xs text-[#aeb8bf] transition-colors hover:bg-white/12 focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none"
        >
          {t("today.rightRail.askPlaceholder")}
          <Send aria-hidden="true" className="size-4 text-[#f5f7f8]" />
        </Link>
      </section>

      <section className="bg-card border-border/60 rounded-lg border p-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-section font-section text-ink">
            {t("today.rightRail.achievementTitle")}
          </h2>
          <span className="bg-surface-subtle text-muted-foreground text-label rounded-xs px-1.5 py-0.5">
            {t("today.stats.insights.sampleTag")}
          </span>
        </div>
        <ul className="compact:grid-cols-2 mt-5 grid gap-x-4 gap-y-5">
          {achievements.map(([Icon, title, detail]) => (
            <li key={title} className="flex min-w-0 gap-2.5">
              <Icon
                aria-hidden="true"
                className="text-ink mt-0.5 size-5 shrink-0"
              />
              <div className="min-w-0">
                <p className="text-body text-ink font-medium">{title}</p>
                <p className="text-label text-muted-foreground mt-0.5">
                  {detail}
                </p>
              </div>
            </li>
          ))}
        </ul>
        <Link
          to="/chat"
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "mt-5 w-full",
          )}
        >
          {t("today.rightRail.reviewProgress")}
          <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </Link>
      </section>
    </aside>
  );
}
