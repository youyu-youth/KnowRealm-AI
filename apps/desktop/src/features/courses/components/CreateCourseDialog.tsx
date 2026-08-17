import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
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
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import type {
  CourseType,
  EducationStage,
  LearningContext,
  LearningDepth,
} from "@/features/courses/api/types";

const learningContexts: LearningContext[] = ["SCHOOL", "CAREER", "INTEREST"];
const educationStages: EducationStage[] = [
  "MIDDLE_SCHOOL",
  "HIGH_SCHOOL",
  "UNDERGRADUATE",
  "GRADUATE",
  "DOCTORAL",
];
const learningDepths: LearningDepth[] = [
  "BEGINNER",
  "INTERMEDIATE",
  "ADVANCED",
];
const courseTypes: CourseType[] = ["MAJOR", "GENERAL", "ELECTIVE"];
const NO_COURSE_TYPE = "NONE";

type CreateCourseDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CreateCourseDialog({
  open,
  onOpenChange,
}: CreateCourseDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [learningContext, setLearningContext] =
    useState<LearningContext>("SCHOOL");
  const [educationStage, setEducationStage] = useState<EducationStage | "">("");
  const [depth, setDepth] = useState<LearningDepth | "">("");
  const [courseType, setCourseType] = useState<CourseType | "">("");
  const [description, setDescription] = useState("");
  const learningContextItems = learningContexts.map((value) => ({
    value,
    label: t(`spaces.learningContext.${value}`),
  }));
  const educationStageItems = educationStages.map((value) => ({
    value,
    label: t(`spaces.educationStage.${value}`),
  }));
  const learningDepthItems = learningDepths.map((value) => ({
    value,
    label: t(`spaces.depth.${value}`),
  }));
  const courseTypeItems: Array<{
    value: CourseType | typeof NO_COURSE_TYPE;
    label: string;
  }> = [
    { value: NO_COURSE_TYPE, label: t("spaces.form.courseTypeNone") },
    ...courseTypes.map((value) => ({
      value,
      label: t(`spaces.courseType.${value}`),
    })),
  ];
  const createCourse = useMutation({
    mutationFn: courseApi.create,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: courseKeys.list() });
      resetForm();
      onOpenChange(false);
    },
  });

  const requiredContextSelected =
    learningContext === "SCHOOL" ? educationStage !== "" : depth !== "";
  const canSubmit = name.trim().length > 0 && requiredContextSelected;

  function resetForm() {
    setName("");
    setLearningContext("SCHOOL");
    setEducationStage("");
    setDepth("");
    setCourseType("");
    setDescription("");
    createCourse.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && !createCourse.isPending) resetForm();
    onOpenChange(nextOpen);
  }

  function handleLearningContext(value: LearningContext | null) {
    if (value === null) return;
    setLearningContext(value);
    if (value === "SCHOOL") setDepth("");
    else setEducationStage("");
  }

  function handleCourseType(value: string | null) {
    if (value === "MAJOR" || value === "GENERAL" || value === "ELECTIVE") {
      setCourseType(value);
    } else {
      setCourseType("");
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    createCourse.mutate({
      name,
      learning_context: learningContext,
      education_stage:
        learningContext === "SCHOOL" ? educationStage || null : null,
      depth: learningContext === "SCHOOL" ? null : depth || null,
      course_type: courseType || null,
      description: description || null,
    });
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={false}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{t("spaces.form.title")}</DialogTitle>
            <DialogDescription>
              {t("spaces.form.description")}
            </DialogDescription>
          </DialogHeader>

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="course-name">
                {t("spaces.form.name")}
              </FieldLabel>
              <Input
                id="course-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
                maxLength={100}
                required
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="learning-context">
                {t("spaces.form.learningContext")}
              </FieldLabel>
              <Select
                items={learningContextItems}
                value={learningContext}
                onValueChange={handleLearningContext}
              >
                <SelectTrigger id="learning-context" className="w-full">
                  <SelectValue>
                    {t(`spaces.learningContext.${learningContext}`)}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {learningContexts.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(`spaces.learningContext.${value}`)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>
                {t("spaces.form.learningContextHint")}
              </FieldDescription>
            </Field>

            {learningContext === "SCHOOL" ? (
              <Field>
                <FieldLabel htmlFor="education-stage">
                  {t("spaces.form.educationStage")}
                </FieldLabel>
                <Select
                  items={educationStageItems}
                  value={educationStage || null}
                  onValueChange={(value) => setEducationStage(value ?? "")}
                >
                  <SelectTrigger
                    id="education-stage"
                    className="w-full"
                    aria-required="true"
                  >
                    <SelectValue
                      placeholder={t("spaces.form.educationStagePlaceholder")}
                    >
                      {educationStage
                        ? t(`spaces.educationStage.${educationStage}`)
                        : null}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {educationStages.map((value) => (
                        <SelectItem key={value} value={value}>
                          {t(`spaces.educationStage.${value}`)}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            ) : (
              <Field>
                <FieldLabel htmlFor="learning-depth">
                  {t("spaces.form.depth")}
                </FieldLabel>
                <Select
                  items={learningDepthItems}
                  value={depth || null}
                  onValueChange={(value) => setDepth(value ?? "")}
                >
                  <SelectTrigger
                    id="learning-depth"
                    className="w-full"
                    aria-required="true"
                  >
                    <SelectValue
                      placeholder={t("spaces.form.depthPlaceholder")}
                    >
                      {depth ? t(`spaces.depth.${depth}`) : null}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {learningDepths.map((value) => (
                        <SelectItem key={value} value={value}>
                          {t(`spaces.depth.${value}`)}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            )}

            <Field>
              <FieldLabel htmlFor="course-type">
                {t("spaces.form.courseType")}
              </FieldLabel>
              <Select
                items={courseTypeItems}
                value={courseType || NO_COURSE_TYPE}
                onValueChange={handleCourseType}
              >
                <SelectTrigger id="course-type" className="w-full">
                  <SelectValue>
                    {courseType
                      ? t(`spaces.courseType.${courseType}`)
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
                        {t(`spaces.courseType.${value}`)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>

            <Field>
              <FieldLabel htmlFor="course-description">
                {t("spaces.form.courseDescription")}
              </FieldLabel>
              <Textarea
                id="course-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
              />
            </Field>
          </FieldGroup>

          {createCourse.isError ? (
            <Alert variant="destructive">
              <AlertDescription>{createCourse.error.message}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              {t("spaces.form.cancel")}
            </DialogClose>
            <Button
              type="submit"
              disabled={!canSubmit || createCourse.isPending}
            >
              {createCourse.isPending ? (
                <Spinner
                  data-icon="inline-start"
                  aria-label={t("spaces.form.saving")}
                />
              ) : null}
              {t("spaces.form.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
