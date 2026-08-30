import type {
  CourseType,
  EducationStage,
  LearningContext,
  LearningDepth,
} from "@/features/courses/api/types";
import type { ProfileOut } from "@/features/settings/api/profile";

type PrimaryRole = NonNullable<ProfileOut["primary_role"]>;

export type CourseFormValues = {
  name: string;
  learningContext: LearningContext | "";
  educationStage: EducationStage | "";
  depth: LearningDepth | "";
  courseType: CourseType | "";
  description: string;
};

export type CourseFieldId = keyof CourseFormValues;

export const emptyCourseFormValues: CourseFormValues = {
  name: "",
  learningContext: "",
  educationStage: "",
  depth: "",
  courseType: "",
  description: "",
};

// 建课按角色预选默认学习场景（STUDENT→学业、职场角色→职业）；无档案/OTHER 不预选。
const ROLE_PRESET_CONTEXT: Record<
  Exclude<PrimaryRole, "OTHER">,
  LearningContext
> = {
  STUDENT: "SCHOOL",
  DEVELOPER: "CAREER",
  OFFICE_WORKER: "CAREER",
};

/** 角色对应的预选学习场景；无档案/OTHER 返回空（由用户自选）。 */
export function presetLearningContext(
  role: PrimaryRole | null,
): LearningContext | "" {
  return role !== null && role !== "OTHER" ? ROLE_PRESET_CONTEXT[role] : "";
}

export function initialCourseFormValues(
  role: PrimaryRole | null,
): CourseFormValues {
  return {
    ...emptyCourseFormValues,
    learningContext: presetLearningContext(role),
  };
}

export function courseFormValuesFromCourse(course: {
  name: string;
  learning_context: LearningContext;
  education_stage: EducationStage | null;
  depth: LearningDepth | null;
  course_type: CourseType | null;
  description: string | null;
}): CourseFormValues {
  return {
    name: course.name,
    learningContext: course.learning_context,
    educationStage: course.education_stage ?? "",
    depth: course.depth ?? "",
    courseType: course.course_type ?? "",
    description: course.description ?? "",
  };
}

export function courseFieldId(field: CourseFieldId): string {
  return `course-field-${field}`;
}

/** 客户端可校验的必填字段（学习场景未选或切换后互斥字段随之必填）。 */
export type CourseRequiredField = Exclude<
  CourseFieldId,
  "courseType" | "description"
>;

/** 返回违反必填或跨字段约束的字段；null 表示表单值可提交。 */
export function invalidCourseFormField(
  values: CourseFormValues,
): CourseRequiredField | null {
  if (values.name.trim().length === 0) {
    return "name";
  }
  if (values.learningContext === "") {
    return "learningContext";
  }
  if (values.learningContext === "SCHOOL" && values.educationStage === "") {
    return "educationStage";
  }
  if (values.learningContext !== "SCHOOL" && values.depth === "") {
    return "depth";
  }
  return null;
}

export type CourseFormPayload = {
  name: string;
  learning_context: LearningContext;
  education_stage: EducationStage | null;
  depth: LearningDepth | null;
  course_type: CourseType | null;
  description: string | null;
};

export function courseFormPayloadFromValues(
  values: CourseFormValues,
): CourseFormPayload {
  // 提交按钮由 invalidCourseFormField 把关，此处仅收窄"场景已选"的类型。
  if (values.learningContext === "") {
    throw new Error("学习场景未选择");
  }
  return {
    name: values.name,
    learning_context: values.learningContext,
    education_stage:
      values.learningContext === "SCHOOL"
        ? values.educationStage || null
        : null,
    depth: values.learningContext === "SCHOOL" ? null : values.depth || null,
    course_type: values.courseType || null,
    description: values.description || null,
  };
}
