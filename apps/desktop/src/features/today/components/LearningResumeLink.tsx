import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import type { ResumeTarget } from "@/features/today/resumeTarget";

export function LearningResumeLink({
  target,
  children,
  className,
}: {
  target: ResumeTarget;
  children: ReactNode;
  className?: string;
}) {
  if (target.kind === "RECORD") {
    const tab = target.record_tab;
    return (
      <Link
        to="/records/$recordId"
        params={{ recordId: target.target_id }}
        search={{ tab: tab === "summary" || !tab ? undefined : tab }}
        className={className}
      >
        {children}
      </Link>
    );
  }
  if (target.kind === "QUIZ_TEST" && target.course_id) {
    return (
      <Link
        to="/spaces/$courseId/tests/$testId"
        params={{ courseId: target.course_id, testId: target.target_id }}
        className={className}
      >
        {children}
      </Link>
    );
  }
  if (target.kind === "CHAT_SESSION") {
    return (
      <Link
        to="/chat/$sessionId"
        params={{ sessionId: target.target_id }}
        className={className}
      >
        {children}
      </Link>
    );
  }
  return <>{children}</>;
}
