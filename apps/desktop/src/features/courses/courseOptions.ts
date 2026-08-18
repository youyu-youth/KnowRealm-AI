import type {
  CourseType,
  EducationStage,
  LearningContext,
  LearningDepth,
} from "@/features/courses/api/types";

export const learningContextLabelKeys = {
  SCHOOL: "spaces.learningContext.SCHOOL",
  CAREER: "spaces.learningContext.CAREER",
  INTEREST: "spaces.learningContext.INTEREST",
} satisfies Record<LearningContext, string>;

export const educationStageLabelKeys = {
  MIDDLE_SCHOOL: "spaces.educationStage.MIDDLE_SCHOOL",
  HIGH_SCHOOL: "spaces.educationStage.HIGH_SCHOOL",
  UNDERGRADUATE: "spaces.educationStage.UNDERGRADUATE",
  GRADUATE: "spaces.educationStage.GRADUATE",
  DOCTORAL: "spaces.educationStage.DOCTORAL",
} satisfies Record<EducationStage, string>;

export const learningDepthLabelKeys = {
  BEGINNER: "spaces.depth.BEGINNER",
  INTERMEDIATE: "spaces.depth.INTERMEDIATE",
  ADVANCED: "spaces.depth.ADVANCED",
} satisfies Record<LearningDepth, string>;

export const courseTypeLabelKeys = {
  MAJOR: "spaces.courseType.MAJOR",
  GENERAL: "spaces.courseType.GENERAL",
  ELECTIVE: "spaces.courseType.ELECTIVE",
} satisfies Record<CourseType, string>;

function keysOf<T extends string>(mapping: Record<T, string>): T[] {
  // Object.keys preserves this exhaustive Record's own string keys.
  return Object.keys(mapping) as T[];
}

export const learningContexts = keysOf(learningContextLabelKeys);
export const educationStages = keysOf(educationStageLabelKeys);
export const learningDepths = keysOf(learningDepthLabelKeys);
export const courseTypes = keysOf(courseTypeLabelKeys);

/** 教育阶段（SCHOOL）或学习深度（其余场景）的展示文案 key；均缺省时为 null。 */
export function courseLevelLabelKey(course: {
  education_stage: EducationStage | null;
  depth: LearningDepth | null;
}): string | null {
  if (course.education_stage) {
    return educationStageLabelKeys[course.education_stage];
  }
  if (course.depth) {
    return learningDepthLabelKeys[course.depth];
  }
  return null;
}

export const courseDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

export function isEducationStage(value: unknown): value is EducationStage {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(educationStageLabelKeys, value)
  );
}

export function isCourseType(value: unknown): value is CourseType {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(courseTypeLabelKeys, value)
  );
}
