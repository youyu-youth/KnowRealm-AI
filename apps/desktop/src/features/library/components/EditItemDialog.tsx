import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useActiveCourses } from "@/features/courses/api/queries";
import {
  useLibraryItemEdit,
  type LibraryItemOut,
} from "@/features/library/api/library";

const UNCLASSIFIED = "__unclassified__";

/**
 * 资料条目编辑对话框（工单 05）：重命名 + 归类/取消归类。
 * 派生 Record 不随归类移动（后端语义），对话框内如实提示。
 * 调用方须条件挂载（open 时才渲染）：表单初始值取自挂载时的 item。
 */
export function EditItemDialog({
  open,
  onOpenChange,
  item,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: LibraryItemOut;
}) {
  const { t } = useTranslation();
  const { courses } = useActiveCourses();
  const edit = useLibraryItemEdit();
  const [title, setTitle] = useState(item.title);
  const [courseValue, setCourseValue] = useState<string>(
    item.course_id ?? UNCLASSIFIED,
  );

  const submit = () => {
    const body: {
      title?: string;
      course_id?: string | null;
    } = {};
    if (title.trim() && title.trim() !== item.title) body.title = title.trim();
    const nextCourse =
      courseValue === UNCLASSIFIED ? null : (courseValue ?? null);
    if (nextCourse !== item.course_id) body.course_id = nextCourse;
    if (Object.keys(body).length === 0) {
      onOpenChange(false);
      return;
    }
    edit.mutate(
      { itemId: item.id, body },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("library.edit.title")}</DialogTitle>
          <DialogDescription>{t("library.edit.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel htmlFor="library-item-title">
              {t("library.edit.titleLabel")}
            </FieldLabel>
            <Input
              id="library-item-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-label={t("library.edit.titleLabel")}
            />
          </Field>
          <Field>
            <FieldLabel>{t("library.edit.courseLabel")}</FieldLabel>
            <Select
              items={[
                {
                  value: UNCLASSIFIED,
                  label: t("library.filters.unclassified"),
                },
                ...courses.map((course) => ({
                  value: course.id,
                  label: course.name,
                })),
              ]}
              value={courseValue}
              onValueChange={(value) => setCourseValue(value ?? UNCLASSIFIED)}
            >
              <SelectTrigger
                className="w-full"
                aria-label={t("library.edit.courseLabel")}
              >
                <SelectValue>
                  {courseValue === UNCLASSIFIED
                    ? t("library.filters.unclassified")
                    : (courses.find((course) => course.id === courseValue)
                        ?.name ?? null)}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={UNCLASSIFIED}>
                    {t("library.filters.unclassified")}
                  </SelectItem>
                  {courses.map((course) => (
                    <SelectItem key={course.id} value={course.id}>
                      {course.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <FieldDescription>{t("library.edit.courseHint")}</FieldDescription>
          </Field>
          {edit.isError ? (
            <p role="alert" className="text-destructive text-label">
              {edit.error.message}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("library.edit.cancel")}
          </Button>
          <Button
            onClick={submit}
            disabled={edit.isPending || title.trim().length === 0}
          >
            {t("library.edit.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
