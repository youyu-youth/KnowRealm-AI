import type { TFunction } from "i18next";
import type {
  ConceptMastery,
  CourseMastery,
  MasteryEvidenceItem,
} from "@/features/courses/api/types";

export const EXAMPLE_COURSE = "example";

export function exampleProfile(t: TFunction): CourseMastery {
  const statuses = [
    "WEAK",
    "STABLE",
    "LEARNING",
    "NOT_ENOUGH_DATA",
    "STABLE",
    "LEARNING",
    "WEAK",
    "NOT_ENOUGH_DATA",
  ] as const;
  const concepts: ConceptMastery[] = statuses.map((status, index) => ({
    concept_id: `example-${index}`,
    canonical_name: t(`learningProfile.example.concept${index}`),
    description: t(`learningProfile.example.description${index}`),
    concept_type: "PRINCIPLE",
    importance: 3,
    status,
    mastery_score:
      status === "NOT_ENOUGH_DATA"
        ? null
        : status === "STABLE"
          ? 0.9
          : status === "WEAK"
            ? 0.35
            : 0.65,
    confidence: status === "NOT_ENOUGH_DATA" ? null : "MEDIUM",
    evidence_count: status === "NOT_ENOUGH_DATA" ? 0 : 4,
    positive_evidence_count: status === "STABLE" ? 4 : 2,
    negative_evidence_count:
      status === "STABLE" || status === "NOT_ENOUGH_DATA" ? 0 : 2,
    last_practiced_at:
      status === "NOT_ENOUGH_DATA"
        ? null
        : `2026-10-${18 - index}T09:00:00+08:00`,
    last_verified_at:
      status === "NOT_ENOUGH_DATA"
        ? null
        : `2026-10-${18 - index}T09:00:00+08:00`,
  }));
  return {
    course_id: EXAMPLE_COURSE,
    concepts,
    confirmed_concept_count: concepts.length,
    verified_concept_count: 6,
    coverage: 0.75,
    status_counts: { stable: 2, learning: 2, weak: 2, not_enough_data: 2 },
  };
}

export function exampleEvidence(): MasteryEvidenceItem[] {
  return ["CORRECT", "WRONG", "CORRECT", "PARTIAL"].map((result, index) => ({
    evidence_id: `example-evidence-${index}`,
    result,
    score: result === "CORRECT" ? 1 : result === "PARTIAL" ? 0.5 : 0,
    occurred_at: `2026-10-${18 - index}T09:00:00+08:00`,
    source: null,
  }));
}
