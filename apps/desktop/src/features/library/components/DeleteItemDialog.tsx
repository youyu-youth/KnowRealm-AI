import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useLibraryItemAction,
  type LibraryItemDetailOut,
} from "@/features/library/api/library";

/**
 * 删除确认对话框（工单 05）：软删入回收站前展示派生 Record，
 * 明示它们不会被级联删除；回收站中的「彻底删除」走 permanent。
 */
export function DeleteItemDialog({
  open,
  onOpenChange,
  item,
  permanent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: LibraryItemDetailOut | null;
  permanent: boolean;
}) {
  const { t } = useTranslation();
  const action = useLibraryItemAction();
  const submit = () => {
    if (!item) return;
    action.mutate(
      { action: permanent ? "purge" : "delete", itemId: item.id },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      },
    );
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {permanent
              ? t("library.delete.permanentTitle")
              : t("library.delete.title")}
          </DialogTitle>
          <DialogDescription>
            {permanent
              ? t("library.delete.permanentDescription")
              : t("library.delete.description")}
          </DialogDescription>
        </DialogHeader>
        {item && item.derived_records.length > 0 ? (
          <Alert>
            <AlertDescription>
              <p className="mb-1">{t("library.delete.derivedRecordsHint")}</p>
              <ul className="list-disc pl-4">
                {item.derived_records.map((record) => (
                  <li key={record.record_id} className="truncate">
                    {record.title}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : permanent ? null : (
          <p className="text-muted-foreground text-sm">
            {t("library.delete.noDerivedRecords")}
          </p>
        )}
        {action.isError ? (
          <p role="alert" className="text-destructive text-label">
            {action.error.message}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("library.delete.cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={submit}
            disabled={action.isPending}
          >
            {permanent
              ? t("library.delete.permanentConfirm")
              : t("library.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
