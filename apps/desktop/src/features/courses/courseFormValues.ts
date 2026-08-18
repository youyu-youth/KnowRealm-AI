import type {
  CourseType,
  EducationStage,
  LearningContext,
  LearningDepth,
} from "@/features/courses/api/types";

export type CourseFormValues = {
  name: string;
  learningContext: LearningContext;
  educationStage: EducationStage | "";
  depth: LearningDepth | "";
  courseType: CourseType | "";
  description: string;
};

export type CourseFieldId = keyof CourseFormValues;

export const emptyCourseFormValues: CourseFormValues = {
  name: "",
  learningContext: "SCHOOL",
  educationStage: "",
  depth: "",
  courseType: "",
  description: "",
};

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

/** 客户端可校验的必填字段（学习场景切换后互斥字段随之必填）。 */
export type CourseRequiredField = Exclude<
  CourseFieldId,
  "learningContext" | "courseType" | "description"
>;

/** 返回违反必填或跨字段约束的字段；null 表示表单值可提交。 */
export function invalidCourseFormField(
  values: CourseFormValues,
): CourseRequiredField | null {
  if (values.name.trim().length === 0) {
    return "name";
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
