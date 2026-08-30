import { useTranslation } from "react-i18next";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { CourseType, LearningContext } from "@/features/courses/api/types";
import type {
  CourseFieldId,
  CourseFormValues,
} from "@/features/courses/courseFormValues";
import { courseFieldId } from "@/features/courses/courseFormValues";
import {
  courseTypeLabelKeys,
  courseTypes,
  educationStageLabelKeys,
  educationStages,
  learningContextLabelKeys,
  learningContexts,
  learningDepthLabelKeys,
  learningDepths,
} from "@/features/courses/courseOptions";

const NO_COURSE_TYPE = "NONE";

type CourseFormFieldsProps = {
  values: CourseFormValues;
  onChange: (patch: Partial<CourseFormValues>) => void;
  errors?: Partial<Record<CourseFieldId, string>>;
};

export function CourseFormFields({
  values,
  onChange,
  errors = {},
}: CourseFormFieldsProps) {
  const { t } = useTranslation();
  const learningContextItems = learningContexts.map((value) => ({
    value,
    label: t(learningContextLabelKeys[value]),
  }));
  const educationStageItems = educationStages.map((value) => ({
    value,
    label: t(educationStageLabelKeys[value]),
  }));
  const learningDepthItems = learningDepths.map((value) => ({
    value,
    label: t(learningDepthLabelKeys[value]),
  }));
  const courseTypeItems: Array<{
    value: CourseType | typeof NO_COURSE_TYPE;
    label: string;
  }> = [
    { value: NO_COURSE_TYPE, label: t("spaces.form.courseTypeNone") },
    ...courseTypes.map((value) => ({
      value,
      label: t(courseTypeLabelKeys[value]),
    })),
  ];

  function handleLearningContext(value: LearningContext | null) {
    if (value === null) return;
    onChange(
      value === "SCHOOL"
        ? { learningContext: value, depth: "" }
        : { learningContext: value, educationStage: "" },
    );
  }

  function handleCourseType(value: string | null) {
    if (value === "MAJOR" || value === "GENERAL" || value === "ELECTIVE") {
      onChange({ courseType: value });
    } else {
      onChange({ courseType: "" });
    }
  }

  return (
    <FieldGroup>
      <Field data-invalid={errors.name ? true : undefined}>
        <FieldLabel htmlFor={courseFieldId("name")}>
          {t("spaces.form.name")}
        </FieldLabel>
        <Input
          id={courseFieldId("name")}
          value={values.name}
          onChange={(event) => onChange({ name: event.target.value })}
          aria-invalid={errors.name ? true : undefined}
          autoFocus
          maxLength={100}
          required
        />
        {errors.name ? <FieldError>{errors.name}</FieldError> : null}
      </Field>

      <Field data-invalid={errors.learningContext ? true : undefined}>
        <FieldLabel htmlFor={courseFieldId("learningContext")}>
          {t("spaces.form.learningContext")}
        </FieldLabel>
        <Select
          items={learningContextItems}
          value={values.learningContext || null}
          onValueChange={handleLearningContext}
        >
          <SelectTrigger
            id={courseFieldId("learningContext")}
            className="w-full"
            aria-required="true"
            aria-invalid={errors.learningContext ? true : undefined}
          >
            <SelectValue
              placeholder={t("spaces.form.learningContextPlaceholder")}
            >
              {values.learningContext
                ? t(learningContextLabelKeys[values.learningContext])
                : null}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {learningContexts.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(learningContextLabelKeys[value])}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        {errors.learningContext ? (
          <FieldError>{errors.learningContext}</FieldError>
        ) : null}
        <FieldDescription>
          {t("spaces.form.learningContextHint")}
        </FieldDescription>
      </Field>

      {values.learningContext === "SCHOOL" ? (
        <Field data-invalid={errors.educationStage ? true : undefined}>
          <FieldLabel htmlFor={courseFieldId("educationStage")}>
            {t("spaces.form.educationStage")}
          </FieldLabel>
          <Select
            items={educationStageItems}
            value={values.educationStage || null}
            onValueChange={(value) => onChange({ educationStage: value ?? "" })}
          >
            <SelectTrigger
              id={courseFieldId("educationStage")}
              className="w-full"
              aria-required="true"
              aria-invalid={errors.educationStage ? true : undefined}
            >
              <SelectValue
                placeholder={t("spaces.form.educationStagePlaceholder")}
              >
                {values.educationStage
                  ? t(educationStageLabelKeys[values.educationStage])
                  : null}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {educationStages.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(educationStageLabelKeys[value])}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {errors.educationStage ? (
            <FieldError>{errors.educationStage}</FieldError>
          ) : null}
        </Field>
      ) : (
        <Field data-invalid={errors.depth ? true : undefined}>
          <FieldLabel htmlFor={courseFieldId("depth")}>
            {t("spaces.form.depth")}
          </FieldLabel>
          <Select
            items={learningDepthItems}
            value={values.depth || null}
            onValueChange={(value) => onChange({ depth: value ?? "" })}
          >
            <SelectTrigger
              id={courseFieldId("depth")}
              className="w-full"
              aria-required="true"
              aria-invalid={errors.depth ? true : undefined}
            >
              <SelectValue placeholder={t("spaces.form.depthPlaceholder")}>
                {values.depth ? t(learningDepthLabelKeys[values.depth]) : null}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {learningDepths.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(learningDepthLabelKeys[value])}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {errors.depth ? <FieldError>{errors.depth}</FieldError> : null}
        </Field>
      )}

      <Field>
        <FieldLabel htmlFor={courseFieldId("courseType")}>
          {t("spaces.form.courseType")}
        </FieldLabel>
        <Select
          items={courseTypeItems}
          value={values.courseType || NO_COURSE_TYPE}
          onValueChange={handleCourseType}
        >
          <SelectTrigger id={courseFieldId("courseType")} className="w-full">
            <SelectValue>
              {values.courseType
                ? t(courseTypeLabelKeys[values.courseType])
                : t("spaces.form.courseTypeNone")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value={NO_COURSE_TYPE}>
                {t("spaces.form.courseTypeNone")}
              </SelectItem>
              {courseTypes.map((value) => (
                <SelectItem key={value} value={value}>
                  {t(courseTypeLabelKeys[value])}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>

      <Field>
        <FieldLabel htmlFor={courseFieldId("description")}>
          {t("spaces.form.courseDescription")}
        </FieldLabel>
        <Textarea
          id={courseFieldId("description")}
          value={values.description}
          onChange={(event) => onChange({ description: event.target.value })}
          rows={3}
        />
      </Field>
    </FieldGroup>
  );
}
