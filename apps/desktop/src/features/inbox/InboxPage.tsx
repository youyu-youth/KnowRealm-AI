import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordOut } from "@/features/records/api/types";
import {
  captureTypeLabelKeys,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";

export function InboxPage() {
  const { t } = useTranslation();
  const records = useQuery({
    queryKey: recordKeys.inbox(),
    queryFn: () => recordApi.listInbox(),
    refetchInterval: (query) =>
      query.state.data?.some((record) => record.status === "CONTENT_PROCESSING")
        ? 2_000
        : false,
  });

  if (records.isPending) {
    return (
      <section className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("inbox.title")}
        </h1>
        <p
          role="status"
          className="text-body text-muted-foreground mt-6 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("inbox.loading")}
        </p>
      </section>
    );
  }

  if (records.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("inbox.title")}
        </h1>
        <h2 className="text-section font-section text-ink mt-6">
          {t("inbox.errorTitle")}
        </h2>
        <p className="max-w-reading text-body text-muted-foreground mt-2">
          {records.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void records.refetch()}
        >
          {t("inbox.retry")}
        </Button>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto min-w-0 py-8">
      <h1 className="text-headline font-headline text-ink-strong">
        {t("inbox.title")}
      </h1>
      <p className="max-w-reading text-body text-muted-foreground mt-2">
        {t("inbox.description")}
      </p>
      {records.data.length === 0 ? (
        <Empty className="border-border mt-8 items-start rounded-none border-t p-0 pt-8 text-start">
          <EmptyHeader className="items-start text-start">
            <h2 className="text-section font-section text-ink">
              {t("inbox.emptyTitle")}
            </h2>
            <EmptyDescription className="max-w-reading text-body">
              {t("inbox.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ul
          aria-label={t("inbox.listLabel")}
          className="border-border mt-8 border-t"
        >
          {records.data.map((record) => (
            <InboxRow key={record.id} record={record} />
          ))}
        </ul>
      )}
    </section>
  );
}

function InboxRow({ record }: { record: RecordOut }) {
  const { t } = useTranslation();
  const title = record.title.trim() || t("spaces.records.untitled");
  return (
    <li className="border-border flex min-w-0 items-center gap-2 border-b last:border-b-0">
      <Link
        to="/records/$recordId"
        params={{ recordId: record.id }}
        search={{ tab: "transcript" }}
        className="hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-sm px-2 py-4 transition-colors focus-visible:ring-3"
      >
        <div className="min-w-0">
          <h2
            className="text-body font-section text-ink truncate"
            title={title}
          >
            {title}
          </h2>
          <div className="text-label text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{t(captureTypeLabelKeys[record.capture_type])}</span>
            <span aria-hidden="true">·</span>
            <time dateTime={record.created_at}>
              {t("spaces.records.createdAt", {
                date: recordDateFormatter.format(new Date(record.created_at)),
              })}
            </time>
          </div>
        </div>
        <span
          className={`${statusClassNames[record.status]} text-label font-label rounded-xs px-2 py-1 whitespace-nowrap`}
        >
          {t(statusLabelKeys[record.status])}
        </span>
      </Link>
      <InboxDeleteButton recordId={record.id} title={title} />
    </li>
  );
}

function InboxDeleteButton({
  recordId,
  title,
}: {
  recordId: string;
  title: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const deleteRecord = useMutation({
    mutationFn: () => recordApi.delete(recordId),
    onSuccess: async () => {
      queryClient.removeQueries({
        queryKey: recordKeys.detail(recordId),
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: recordKeys.transcript(recordId),
        exact: true,
      });
      await queryClient.invalidateQueries({ queryKey: recordKeys.inbox() });
      setOpen(false);
    },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (deleteRecord.isPending) return;
    if (!nextOpen) deleteRecord.reset();
    setOpen(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("inbox.delete.action", { title })}
          />
        }
      >
        <Trash2 aria-hidden="true" />
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("inbox.delete.title")}</DialogTitle>
          <DialogDescription className="break-words">
            {t("inbox.delete.description", { title })}
          </DialogDescription>
        </DialogHeader>
        {deleteRecord.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{deleteRecord.error.message}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            {t("inbox.delete.cancel")}
          </DialogClose>
          <Button
            variant="destructive"
            onClick={() => deleteRecord.mutate()}
            disabled={deleteRecord.isPending}
          >
            {deleteRecord.isPending ? (
              <Spinner
                data-icon="inline-start"
                aria-label={t("inbox.delete.deleting")}
              />
            ) : null}
            {t("inbox.delete.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
