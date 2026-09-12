import { useTranslation } from "react-i18next";

/** 右栏寄语卡：静态引用 + 极简山形装饰。 */
export function CourseQuoteCard() {
  const { t } = useTranslation();
  return (
    <section className="border-border bg-surface-raised relative overflow-hidden rounded-xl border p-4">
      <blockquote className="text-body-dense text-ink-muted leading-relaxed">
        <p>“{t("spaces.courseDetail.quote.text")}”</p>
        <footer className="text-label text-ink-faint mt-2">— KnowRealm</footer>
      </blockquote>
      <svg
        viewBox="0 0 200 64"
        aria-hidden="true"
        className="text-ink-faint/50 mt-3 h-16 w-full"
        preserveAspectRatio="none"
      >
        <path
          d="M0 60 L38 26 L64 46 L96 14 L128 42 L158 22 L200 58"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
        />
        <path
          d="M0 64 L52 40 L88 56 L124 34 L164 52 L200 64 Z"
          fill="currentColor"
          fillOpacity="0.12"
        />
      </svg>
      <p className="text-label text-ink-faint mt-1 flex items-center justify-between">
        <span>Continue Learning</span>
        <span>A Better You</span>
      </p>
    </section>
  );
}
