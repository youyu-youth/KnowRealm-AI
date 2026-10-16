import { useContext, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  ClipboardPaste,
  FilePlus2,
  Scissors,
  Mic,
  HardDrive,
  NotebookPen,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { CaptureActionsContext } from "@/components/layout/captureActionsContext";
import { AddLibraryItemDialog } from "@/features/library/components/AddLibraryItemDialog";
import type { CourseDetail } from "@/features/courses/api/types";

export function CourseCaptureDock({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const openCapture = useContext(CaptureActionsContext);
  const [clipOpen, setClipOpen] = useState(false);
  const archived = course.status === "ARCHIVED";

  function openItem(itemId: string) {
    setClipOpen(false);
    void navigate({ to: "/library", search: { sel: itemId, selType: "item" } });
  }

  return (
    <>
      <footer
        className="course-capture-dock"
        aria-label={t("spaces.courseDetail.capture.label")}
      >
        <div className="course-capture-actions">
          <Button
            variant="outline"
            size="sm"
            disabled={!openCapture}
            onClick={() => openCapture?.("capture.note")}
          >
            <NotebookPen aria-hidden="true" />
            {t("capture.note")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={archived || !openCapture}
            onClick={() => openCapture?.("capture.import")}
          >
            <FilePlus2 aria-hidden="true" />
            {t("capture.import")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={archived || !openCapture}
            onClick={() => openCapture?.("capture.paste")}
          >
            <ClipboardPaste aria-hidden="true" />
            {t("capture.paste")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={archived}
            onClick={() => setClipOpen(true)}
          >
            <Scissors aria-hidden="true" />
            {t("spaces.courseDetail.capture.clip")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={archived || !openCapture}
            onClick={() => openCapture?.("capture.record")}
          >
            <Mic aria-hidden="true" />
            {t("capture.record")}
          </Button>
        </div>
        <p className="course-capture-hint">
          {t(
            archived
              ? "spaces.courseDetail.capture.archived"
              : "spaces.courseDetail.capture.hint",
          )}
        </p>
        <span className="course-local-state">
          <HardDrive className="size-3.5" aria-hidden="true" />
          {t("spaces.courseDetail.capture.local")}
        </span>
      </footer>
      {clipOpen && (
        <AddLibraryItemDialog
          open
          initial={{ tab: "web", courseId: course.id }}
          onOpenChange={setClipOpen}
          onOpenItem={openItem}
          onAccepted={({ item }) => openItem(item.id)}
        />
      )}
    </>
  );
}
