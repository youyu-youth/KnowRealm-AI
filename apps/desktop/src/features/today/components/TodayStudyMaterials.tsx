import { useState } from "react";
import { ChevronLeft, ChevronRight, FileText, NotebookPen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { materialExamples } from "@/features/today/materialExamples";

export function TodayStudyMaterials({
  selected,
  onSelect,
}: {
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useTranslation();
  const [note, setNote] = useState("");
  const material = materialExamples[selected];
  return (
    <section
      className="today-panel today-study-materials"
      aria-label={t("today.redesign.materials")}
    >
      <Tabs defaultValue="materials" className="gap-0">
        <div className="today-material-toolbar">
          <TabsList variant="line">
            <TabsTrigger value="materials">
              {t("today.redesign.materials")}
            </TabsTrigger>
            <TabsTrigger value="notes">{t("today.redesign.notes")}</TabsTrigger>
          </TabsList>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("today.redesign.previousMaterial")}
              onClick={() =>
                onSelect(
                  (selected + materialExamples.length - 1) %
                    materialExamples.length,
                )
              }
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("today.redesign.nextMaterial")}
              onClick={() => onSelect((selected + 1) % materialExamples.length)}
            >
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
        </div>
        <TabsContent value="materials" className="m-0 p-4" keepMounted>
          <div className="today-material-preview">
            <div className="today-material-cover" aria-hidden="true">
              <FileText />
              <span>{material.filename}</span>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-body font-semibold">
                  {t(`today.redesign.examples.${material.key}.title`)}
                </h3>
                <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
              </div>
              <p className="text-label text-ink-muted mt-2">
                {t(`today.redesign.examples.${material.key}.description`)}
              </p>
              <p className="text-label text-ink-muted mt-3 flex items-center gap-2">
                <FileText className="size-4 shrink-0" aria-hidden="true" />
                {material.filename}
              </p>
            </div>
            <pre
              className="today-material-code"
              tabIndex={0}
              aria-label={t("today.redesign.codePreview")}
            >
              <code>{material.code}</code>
            </pre>
          </div>
          <p className="text-label text-ink-muted mt-2">
            {t("today.redesign.materialSampleHint")}
          </p>
        </TabsContent>
        <TabsContent value="notes" className="m-0 p-4" keepMounted>
          <label
            htmlFor="today-session-note"
            className="text-label text-ink-muted mb-2 flex items-center gap-2"
          >
            <NotebookPen className="size-4" aria-hidden="true" />
            {t("today.redesign.noteHint")}
          </label>
          <Textarea
            id="today-session-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={t("today.redesign.notePlaceholder")}
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}
