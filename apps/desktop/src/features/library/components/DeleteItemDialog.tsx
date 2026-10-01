import { useNavigate } from "@tanstack/react-router";
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
 *
 * 彻底删除前置拦截（派生记录防线的前端闭环）：detail 的 derived_records
 * 与后端 purge 防线同口径（仅未软删记录），非空时彻底删除必然被
 * LIBRARY_ITEM_HAS_DERIVED_RECORDS 拒绝——直接禁用确认并给出可跳转的
 * 记录删除路径（记录详情页删除记录后回此处即可彻底删除）。
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
  const navigate = useNavigate();
  const action = useLibraryItemAction();
  const blockedByRecords = permanent && (item?.derived_records.length ?? 0) > 0;
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
              <p className="mb-1">
                {permanent
                  ? t("library.delete.permanentDerivedHint")
                  : t("library.delete.derivedRecordsHint")}
              </p>
              <ul className="list-disc pl-4">
                {item.derived_records.map((record) => (
                  <li key={record.record_id} className="truncate">
                    {permanent ? (
                      <button
                        type="button"
                        className="text-ink underline-offset-2 hover:underline"
                        aria-label={t("library.delete.openRecord", {
                          title: record.title,
                        })}
                        onClick={() => {
                          onOpenChange(false);
                          void navigate({
                            to: "/records/$recordId",
                            params: { recordId: record.record_id },
                          });
                        }}
                      >
                        {record.title}
                      </button>
                    ) : (
                      record.title
                    )}
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
            disabled={action.isPending || blockedByRecords}
            aria-disabled={blockedByRecords || undefined}
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
