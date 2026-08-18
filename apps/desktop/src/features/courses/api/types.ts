import type { components, operations } from "@knowrealm/api-types";

export type Course = components["schemas"]["CourseOut"];
export type CourseCreate = components["schemas"]["CourseCreate"];
export type LearningContext = components["schemas"]["LearningContext"];
export type EducationStage = components["schemas"]["EducationStage"];
export type LearningDepth = components["schemas"]["LearningDepth"];
export type CourseType = components["schemas"]["CourseType"];
export type CourseListQuery = NonNullable<
  operations["list_courses_api_courses_get"]["parameters"]["query"]
>;
