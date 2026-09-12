import { useTranslation } from "react-i18next";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { CourseDetail } from "@/features/courses/api/types";
import { EditCourseForm } from "@/features/courses/components/EditCourseForm";

type CourseEditSheetProps = {
  course: CourseDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** 课程编辑抽屉：复用既有编辑表单；标题与描述由表单内自行渲染。 */
export function CourseEditSheet({
  course,
  open,
  onOpenChange,
}: CourseEditSheetProps) {
  const { t } = useTranslation();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-md">
        <SheetHeader className="sr-only">
          <SheetTitle>{t("spaces.editForm.title")}</SheetTitle>
          <SheetDescription>
            {t("spaces.editForm.description")}
          </SheetDescription>
        </SheetHeader>
        <SheetBody>
          <EditCourseForm
            course={course}
            onCancel={() => onOpenChange(false)}
            onSaved={() => onOpenChange(false)}
          />
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
