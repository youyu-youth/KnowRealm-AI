import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type {
  ReviewMaterialOut,
  ReviewMaterialReadOut,
} from "@/features/records/api/types";
import { ReviewMaterialSections } from "@/features/records/components/ReviewMaterialSections";

type WorkbenchMode = "preview" | "adjust" | "edit";

type ReviewMaterialWorkbenchProps = {
  recordId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 与页签共享的读端点数据：当前版内容、active_job_id、过时标记均来自这里。 */
  read: ReviewMaterialReadOut | undefined;
};

const statusChipClassNames: Record<string, string> = {
  GENERATED: "bg-warning/15 text-warning",
  CONFIRMED: "bg-success/15 text-success",
  SUPERSEDED: "bg-muted text-muted-foreground",
};

export function ReviewMaterialWorkbench({
  recordId,
  open,
  onOpenChange,
  read,
}: ReviewMaterialWorkbenchProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<WorkbenchMode>("preview");
  const [selection, setSelection] = useState<{
    picked: number;
    atVersion: number;
  } | null>(null);
  const [feedback, setFeedback] = useState("");
  const [quickReview, setQuickReview] = useState("");
  const [mindMap, setMindMap] = useState("");
  const [keyList, setKeyList] = useState<string[]>([]);

  const versions = useQuery({
    queryKey: recordKeys.reviewMaterials(recordId),
    queryFn: () => recordApi.getReviewMaterials(recordId),
    enabled: open,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: recordKeys.reviewMaterial(recordId),
    });
    void queryClient.invalidateQueries({
      queryKey: recordKeys.reviewMaterials(recordId),
    });
  };
  const confirm = useMutation({
    mutationFn: () => recordApi.confirmReviewMaterial(recordId),
    onSuccess: () => void refresh(),
  });
  const adjust = useMutation({
    mutationFn: (text: string) =>
      recordApi.adjustReviewMaterial(recordId, { feedback: text }),
    onSuccess: () => {
      setMode("preview");
      void refresh();
    },
  });
  const saveEdit = useMutation({
    mutationFn: () =>
      recordApi.editReviewMaterial(recordId, {
        quick_review: quickReview,
        key_list: keyList.map((item) => item.trim()).filter(Boolean),
        mind_map_markdown: mindMap,
      }),
    onSuccess: () => {
      setMode("preview");
      void refresh();
    },
  });

  const current = read?.review_material;
  // 选中版本只在选中时的那一代当前版本上有效；新版本到达即回到当前版（渲染期派生）
  const selectedVersion =
    selection !== null &&
    current != null &&
    selection.atVersion === current.version_no
      ? selection.picked
      : null;
  const viewing =
    selectedVersion === null
      ? current
      : versions.data?.find((item) => item.version_no === selectedVersion);
  const historical =
    current != null && viewing != null && viewing.id !== current.id;
  const mutationError = confirm.error ?? adjust.error ?? saveEdit.error ?? null;

  function handleOpenChange(nextOpen: boolean) {
    if (confirm.isPending || saveEdit.isPending) return;
    if (!nextOpen) {
      setMode("preview");
      setSelection(null);
      setFeedback("");
      confirm.reset();
      adjust.reset();
      saveEdit.reset();
    }
    onOpenChange(nextOpen);
  }

  function enterEdit(material: ReviewMaterialOut) {
    setQuickReview(material.quick_review);
    setMindMap(material.mind_map_markdown);
    setKeyList(material.key_list);
    setMode("edit");
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <DialogTitle>
              {t("record.detail.review.workbench.title")}
            </DialogTitle>
            {viewing ? (
              <div className="flex items-center gap-2">
                {versions.data && versions.data.length > 1 ? (
                  <Select
                    items={versions.data.map((item) => ({
                      value: String(item.version_no),
                      label: `v${item.version_no}`,
                    }))}
                    value={String(viewing.version_no)}
                    onValueChange={(value) => {
                      const versionNo = Number(value);
                      setSelection(
                        current && versionNo === current.version_no
                          ? null
                          : current
                            ? {
                                picked: versionNo,
                                atVersion: current.version_no,
                              }
                            : null,
                      );
                      setMode("preview");
                      confirm.reset();
                      adjust.reset();
                      saveEdit.reset();
                    }}
                  >
                    <SelectTrigger
                      size="sm"
                      aria-label={t(
                        "record.detail.review.workbench.versionLabel",
                      )}
                    >
                      <SelectValue>{`v${viewing.version_no}`}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {versions.data.map((item) => (
                          <SelectItem
                            key={item.id}
                            value={String(item.version_no)}
                          >
                            {`v${item.version_no} · ${t(
                              `record.detail.review.workbench.versionStatus.${item.status}`,
                            )}`}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : null}
                <span
                  className={`${statusChipClassNames[viewing.status] ?? ""} text-label font-label rounded-xs px-2 py-1`}
                >
                  {t(
                    `record.detail.review.workbench.versionStatus.${viewing.status}`,
                  )}
                </span>
              </div>
            ) : null}
          </div>
          <DialogDescription>
            {t("record.detail.review.workbench.description")}
          </DialogDescription>
        </DialogHeader>

        {read?.transcript_stale && !historical ? (
          <p className="bg-warning/10 text-body text-warning rounded-lg px-3 py-2">
            {t("record.detail.review.workbench.staleNotice")}
          </p>
        ) : null}

        {historical ? (
          <p className="bg-muted/50 text-body text-muted-foreground rounded-lg px-3 py-2">
            {t("record.detail.review.workbench.historicalNotice")}
          </p>
        ) : null}

        <div className="max-h-[60vh] overflow-y-auto pr-1">
          {read?.active_job_id ? (
            <p
              role="status"
              className="text-body text-muted-foreground flex items-center gap-2 py-8"
            >
              <Spinner aria-hidden="true" />
              {t("record.detail.review.workbench.adjusting")}
            </p>
          ) : viewing == null ? (
            <p role="status" className="text-body text-muted-foreground py-8">
              {t("record.detail.review.loading")}
            </p>
          ) : mode === "preview" ? (
            <ReviewMaterialSections material={viewing} />
          ) : mode === "adjust" ? (
            <div className="space-y-2">
              <Label htmlFor="review-adjust-feedback">
                {t("record.detail.review.workbench.adjustFeedbackLabel")}
              </Label>
              <Textarea
                id="review-adjust-feedback"
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                rows={4}
                maxLength={1000}
                className="field-sizing-fixed"
                placeholder={t(
                  "record.detail.review.workbench.adjustFeedbackPlaceholder",
                )}
              />
            </div>
          ) : (
            <div className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="review-edit-quick-review">
                  {t("record.detail.review.workbench.editQuickReviewLabel")}
                </Label>
                <Textarea
                  id="review-edit-quick-review"
                  value={quickReview}
                  onChange={(event) => setQuickReview(event.target.value)}
                  rows={8}
                  maxLength={5000}
                  className="field-sizing-fixed font-mono text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label>
                  {t("record.detail.review.workbench.editKeyListLabel")}
                </Label>
                <div className="space-y-2">
                  {keyList.map((item, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Input
                        value={item}
                        maxLength={80}
                        aria-label={t(
                          "record.detail.review.workbench.editItemLabel",
                          { index: index + 1 },
                        )}
                        onChange={(event) =>
                          setKeyList(
                            keyList.map((entry, entryIndex) =>
                              entryIndex === index ? event.target.value : entry,
                            ),
                          )
                        }
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        disabled={keyList.length <= 1}
                        aria-label={t(
                          "record.detail.review.workbench.editRemoveItem",
                          { index: index + 1 },
                        )}
                        onClick={() =>
                          setKeyList(keyList.filter((_, i) => i !== index))
                        }
                      >
                        <X />
                      </Button>
                    </div>
                  ))}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={keyList.length >= 50}
                  onClick={() => setKeyList([...keyList, ""])}
                >
                  <Plus data-icon="inline-start" aria-hidden="true" />
                  {t("record.detail.review.workbench.editAddItem")}
                </Button>
              </div>
              <div className="space-y-2">
                <Label htmlFor="review-edit-outline">
                  {t("record.detail.review.workbench.editOutlineLabel")}
                </Label>
                <Textarea
                  id="review-edit-outline"
                  value={mindMap}
                  onChange={(event) => setMindMap(event.target.value)}
                  rows={8}
                  maxLength={5000}
                  className="field-sizing-fixed font-mono text-xs"
                />
              </div>
            </div>
          )}
        </div>

        {mutationError ? (
          <p role="alert" className="text-body text-destructive">
            {mutationError.message}
          </p>
        ) : null}

        {read?.active_job_id ? (
          <p className="text-label text-muted-foreground">
            {t("record.detail.review.workbench.adjustingHint")}
          </p>
        ) : mode === "adjust" ? (
          <DialogFooter>
            <Button
              variant="outline"
              disabled={adjust.isPending}
              onClick={() => {
                setMode("preview");
                setFeedback("");
                adjust.reset();
              }}
            >
              {t("record.detail.review.workbench.cancelAdjustment")}
            </Button>
            <Button
              disabled={!feedback.trim() || adjust.isPending}
              onClick={() => feedback.trim() && adjust.mutate(feedback.trim())}
            >
              {adjust.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("record.detail.review.workbench.submitAdjustment")}
            </Button>
          </DialogFooter>
        ) : mode === "edit" ? (
          <DialogFooter>
            <Button
              variant="outline"
              disabled={saveEdit.isPending}
              onClick={() => setMode("preview")}
            >
              {t("record.detail.review.workbench.cancelEdit")}
            </Button>
            <Button
              disabled={
                saveEdit.isPending ||
                !quickReview.trim() ||
                !mindMap.trim() ||
                keyList.every((item) => !item.trim())
              }
              onClick={() => saveEdit.mutate()}
            >
              {saveEdit.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("record.detail.review.workbench.save")}
            </Button>
          </DialogFooter>
        ) : viewing ? (
          <DialogFooter>
            <Button
              variant="outline"
              disabled={historical || confirm.isPending}
              onClick={() => viewing && enterEdit(viewing)}
            >
              {t("record.detail.review.workbench.edit")}
            </Button>
            <Button
              variant="outline"
              disabled={historical || confirm.isPending}
              onClick={() => {
                setFeedback("");
                setMode("adjust");
              }}
            >
              {t("record.detail.review.workbench.adjust")}
            </Button>
            <Button
              disabled={
                historical ||
                viewing.status !== "GENERATED" ||
                confirm.isPending
              }
              onClick={() => confirm.mutate()}
            >
              {confirm.isPending ? <Spinner aria-hidden="true" /> : null}
              {viewing.status === "CONFIRMED"
                ? t("record.detail.review.workbench.confirmed")
                : t("record.detail.review.workbench.confirm")}
            </Button>
          </DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
