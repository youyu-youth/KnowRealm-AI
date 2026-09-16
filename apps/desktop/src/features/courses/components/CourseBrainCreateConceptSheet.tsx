import { useState } from "react";
import { useTranslation } from "react-i18next";

import { appToast } from "@/components/common/appToastManager";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useCreateConcept } from "@/features/courses/api/courseBrain";

// 与抽取提示词一致的五个常见概念类型；其余自由字符串由后端接受。
const CONCEPT_TYPES = ["TERM", "PROCESS", "PRINCIPLE", "METHOD", "TOOL"];
const IMPORTANCE_OPTIONS = [1, 2, 3, 4, 5];

type CourseBrainCreateConceptSheetProps = {
  courseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** 手动创建概念：直接入库为 CONFIRMED（source=USER_CONFIRMED），撞名 409 内联提示。 */
export function CourseBrainCreateConceptSheet({
  courseId,
  open,
  onOpenChange,
}: CourseBrainCreateConceptSheetProps) {
  const { t } = useTranslation();
  const createConcept = useCreateConcept(courseId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [conceptType, setConceptType] = useState("TERM");
  const [importance, setImportance] = useState(3);

  const nameValid = name.trim().length > 0 && name.length <= 100;
  const canSubmit = nameValid && !createConcept.isPending;

  function resetForm() {
    setName("");
    setDescription("");
    setConceptType("TERM");
    setImportance(3);
    createConcept.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && !createConcept.isPending) resetForm();
    onOpenChange(nextOpen);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    createConcept.mutate(
      {
        name: name.trim(),
        description: description.trim(),
        concept_type: conceptType,
        importance,
      },
      {
        onSuccess: (concept) => {
          appToast.add({
            description: t("spaces.courseDetail.brain.create.success", {
              name: concept.canonical_name,
            }),
          });
          onOpenChange(false);
          resetForm();
        },
      },
    );
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <SheetHeader>
            <SheetTitle>
              {t("spaces.courseDetail.brain.create.title")}
            </SheetTitle>
            <SheetDescription>
              {t("spaces.courseDetail.brain.create.description")}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="flex flex-col gap-4">
            <Field>
              <FieldLabel htmlFor="brain-concept-name">
                {t("spaces.courseDetail.brain.create.name")}
              </FieldLabel>
              <Input
                id="brain-concept-name"
                value={name}
                maxLength={100}
                onChange={(event) => setName(event.target.value)}
                autoComplete="off"
                required
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="brain-concept-description">
                {t("spaces.courseDetail.brain.create.descriptionLabel")}
              </FieldLabel>
              <Textarea
                id="brain-concept-description"
                value={description}
                maxLength={2000}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                className="field-sizing-fixed"
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="brain-concept-type">
                {t("spaces.courseDetail.brain.create.type")}
              </FieldLabel>
              <Select
                items={CONCEPT_TYPES.map((value) => ({
                  value,
                  label: t(`spaces.courseDetail.brain.conceptType.${value}`),
                }))}
                value={conceptType}
                onValueChange={(value) => setConceptType(value as string)}
              >
                <SelectTrigger id="brain-concept-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {CONCEPT_TYPES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {t(`spaces.courseDetail.brain.conceptType.${value}`)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>

            <Field>
              <FieldLabel htmlFor="brain-concept-importance">
                {t("spaces.courseDetail.brain.create.importance")}
              </FieldLabel>
              <Select
                items={IMPORTANCE_OPTIONS.map((value) => ({
                  value: String(value),
                  label: String(value),
                }))}
                value={String(importance)}
                onValueChange={(value) => setImportance(Number(value))}
              >
                <SelectTrigger id="brain-concept-importance" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {IMPORTANCE_OPTIONS.map((value) => (
                      <SelectItem key={value} value={String(value)}>
                        {value}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>

            {createConcept.isError ? (
              <Alert variant="destructive">
                <AlertDescription>
                  {createConcept.error.message}
                </AlertDescription>
              </Alert>
            ) : null}
          </SheetBody>

          <SheetFooter>
            <SheetClose
              render={<Button variant="outline" type="button" />}
              disabled={createConcept.isPending}
            >
              {t("spaces.courseDetail.brain.create.cancel")}
            </SheetClose>
            <Button type="submit" disabled={!canSubmit}>
              {createConcept.isPending ? (
                <Spinner aria-hidden="true" data-icon="inline-start" />
              ) : null}
              {t("spaces.courseDetail.brain.create.submit")}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
