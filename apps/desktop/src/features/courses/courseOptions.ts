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
