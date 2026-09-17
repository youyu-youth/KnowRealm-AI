import type { components, operations } from "@knowrealm/api-types";

export type Course = components["schemas"]["CourseOut"];
export type CourseDetail = components["schemas"]["CourseDetailOut"];
export type CourseCreate = components["schemas"]["CourseCreate"];
export type CourseUpdate = components["schemas"]["CourseUpdate"];
export type LearningContext = components["schemas"]["LearningContext"];
export type EducationStage = components["schemas"]["EducationStage"];
export type LearningDepth = components["schemas"]["LearningDepth"];
export type CourseType = components["schemas"]["CourseType"];
export type CourseListQuery = NonNullable<
  operations["list_courses_api_courses_get"]["parameters"]["query"]
>;

export type BrainSnapshot = components["schemas"]["BrainSnapshotOut"];
export type BrainConcept = components["schemas"]["BrainConceptOut"];
export type BrainBuildAccepted = components["schemas"]["BrainBuildAcceptedOut"];
export type ConceptSources = components["schemas"]["ConceptSourcesOut"];
export type ConceptAnchorSource =
  components["schemas"]["ConceptAnchorSourceOut"];
export type ConceptKpSource = components["schemas"]["ConceptKpSourceOut"];
export type BrainGraph = components["schemas"]["BrainGraphOut"];
export type BrainConceptCreate = components["schemas"]["BrainConceptCreate"];
export type BrainApplyReviewRequest =
  components["schemas"]["ApplyReviewRequest"];
export type BrainConceptListQuery = NonNullable<
  operations["list_course_brain_concepts_api_courses__course_id__brain_concepts_get"]["parameters"]["query"]
>;
export type BrainRelation = components["schemas"]["BrainRelationOut"];
export type BrainRelationStatus = components["schemas"]["BrainRelationStatus"];
export type BrainRelationListQuery = NonNullable<
  operations["list_course_brain_relations_api_courses__course_id__brain_relations_get"]["parameters"]["query"]
>;

export type MasteryStatus = components["schemas"]["MasteryStatus"];
export type MasteryConfidence = components["schemas"]["MasteryConfidence"];
export type ConceptMastery = components["schemas"]["ConceptMasteryOut"];
export type CourseMastery = components["schemas"]["CourseMasteryOut"];
export type ConceptMasteryDetail =
  components["schemas"]["ConceptMasteryDetailOut"];
export type MasteryEvidenceItem =
  components["schemas"]["MasteryEvidenceOut"];
export type CourseMasteryQuery = NonNullable<
  operations["get_course_mastery_api_courses__course_id__mastery_get"]["parameters"]["query"]
>;
