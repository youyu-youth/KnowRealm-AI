import { Radio as RadioPrimitive } from "@base-ui/react/radio";
import { useTranslation } from "react-i18next";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
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
  learningContextHintKeys,
  learningDepthLabelKeys,
  learningDepths,
} from "@/features/courses/courseOptions";

const NO_COURSE_TYPE = "NONE";

export const COURSE_DESCRIPTION_MAX_LENGTH = 200;

type CourseFormFieldsProps = {
  values: CourseFormValues;
  onChange: (patch: Partial<CourseFormValues>) => void;
  errors?: Partial<Record<CourseFieldId, string>>;
  /** 创建场景展示只读的「初始状态」，编辑场景不重复展示。 */
  showInitialStatus?: boolean;
};

export function CourseFormFields({
  values,
  onChange,
  errors = {},
  showInitialStatus = false,
}: CourseFormFieldsProps) {
  const { t } = useTranslation();
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

  function handleLearningContext(value: LearningContext) {
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
          <RequiredMark />
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
        <FieldLabel id={courseFieldId("learningContext") + "-label"}>
          {t("spaces.form.learningContext")}
          <RequiredMark />
        </FieldLabel>
        <RadioGroup
          aria-labelledby={courseFieldId("learningContext") + "-label"}
          value={values.learningContext || null}
          onValueChange={handleLearningContext}
          className="grid-cols-3"
        >
          {learningContexts.map((value) => (
            <ContextOption
              key={value}
              value={value}
              id={
                value === "SCHOOL"
                  ? courseFieldId("learningContext")
                  : undefined
              }
              label={t(learningContextLabelKeys[value])}
              hint={t(learningContextHintKeys[value])}
            />
          ))}
        </RadioGroup>
        {errors.learningContext ? (
          <FieldError>{errors.learningContext}</FieldError>
        ) : null}
      </Field>

      {values.learningContext === "SCHOOL" ? (
        <Field data-invalid={errors.educationStage ? true : undefined}>
          <FieldLabel htmlFor={courseFieldId("educationStage")}>
            {t("spaces.form.educationStage")}
            <RequiredMark />
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
            <RequiredMark />
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

      {showInitialStatus ? (
        <Field>
          <FieldLabel htmlFor="course-initial-status">
            {t("spaces.form.initialStatus")}
          </FieldLabel>
          <div
            id="course-initial-status"
            aria-disabled="true"
            className="border-input bg-surface-subtle text-ink-muted flex h-8 items-center rounded-md border px-2.5 text-sm"
          >
            {t("spaces.form.initialStatusValue")}
          </div>
        </Field>
      ) : null}

      <Field>
        <FieldLabel htmlFor={courseFieldId("description")}>
          {t("spaces.form.courseDescription")}
        </FieldLabel>
        <div className="relative">
          <Textarea
            id={courseFieldId("description")}
            value={values.description}
            onChange={(event) => onChange({ description: event.target.value })}
            maxLength={COURSE_DESCRIPTION_MAX_LENGTH}
            rows={3}
            className="pb-7"
          />
          <span
            aria-hidden="true"
            className="text-label text-ink-faint pointer-events-none absolute right-2.5 bottom-2 tabular-nums"
          >
            {values.description.length} / {COURSE_DESCRIPTION_MAX_LENGTH}
          </span>
        </div>
      </Field>
    </FieldGroup>
  );
}

function RequiredMark() {
  return (
    <span className="text-destructive" aria-hidden="true">
      *
    </span>
  );
}

// components/ui 的 RadioGroupItem 不透传 children（生成物固定渲染 Indicator），
// 卡片式场景选择在业务层用 Base UI Radio 原语组合。
function ContextOption({
  value,
  label,
  hint,
  id,
}: {
  value: LearningContext;
  label: string;
  hint: string;
  id?: string;
}) {
  return (
    <RadioPrimitive.Root
      value={value}
      id={id}
      className={cn(
        "border-input bg-background flex min-w-0 flex-col items-start gap-0.5 rounded-md border px-3 py-2.5 text-left transition-colors outline-none",
        "hover:border-border-strong",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3",
        "data-checked:border-foreground data-checked:bg-surface-subtle",
      )}
    >
      <span className="text-body-dense text-ink-strong font-medium">
        {label}
      </span>
      <span className="text-label text-ink-faint">{hint}</span>
    </RadioPrimitive.Root>
  );
}
