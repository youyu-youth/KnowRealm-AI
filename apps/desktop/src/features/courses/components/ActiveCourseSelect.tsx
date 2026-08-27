import { useTranslation } from "react-i18next";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useActiveCourses } from "@/features/courses/api/queries";

type ActiveCourseSelectProps = {
  id: string;
  value: string | null;
  onValueChange: (courseId: string | null) => void;
  disabled?: boolean;
};

export function ActiveCourseSelect({
  id,
  value,
  onValueChange,
  disabled,
}: ActiveCourseSelectProps) {
  const { t } = useTranslation();
  const { courses, isPending, isError } = useActiveCourses();
  return (
    <Field>
      <FieldLabel htmlFor={id}>{t("courseSelect.label")}</FieldLabel>
      <Select
        items={courses.map((course) => ({
          value: course.id,
          label: course.name,
        }))}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled || isPending || courses.length === 0}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={t("courseSelect.placeholder")}>
            {courses.find((course) => course.id === value)?.name ?? null}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {courses.map((course) => (
              <SelectItem key={course.id} value={course.id}>
                {course.name}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      <FieldDescription>
        {isError
          ? t("courseSelect.error")
          : !isPending && courses.length === 0
            ? t("courseSelect.noActive")
            : t("courseSelect.hint")}
      </FieldDescription>
    </Field>
  );
}
