import { BookOpen, Leaf, Network, Workflow } from "lucide-react";
import type { Course } from "@/features/courses/api/types";

export function CourseCover({ course }: { course: Course }) {
  const Icon =
    course.learning_context === "INTEREST"
      ? Leaf
      : course.learning_context === "SCHOOL"
        ? Network
        : Workflow;
  return (
    <div
      className="spaces-cover"
      data-context={course.learning_context}
      aria-hidden="true"
    >
      <span className="spaces-cover-title">{course.name}</span>
      <div className="spaces-cover-diagram">
        <BookOpen className="size-5" />
        <span className="h-px w-6 bg-current opacity-40" />
        <Icon className="size-12" strokeWidth={1} />
      </div>
    </div>
  );
}
