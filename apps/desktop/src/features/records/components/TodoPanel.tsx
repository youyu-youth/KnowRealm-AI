import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { TodoOut } from "@/features/records/api/types";
import type { components } from "@knowrealm/api-types";
import { settingsApi } from "@/features/settings/api/settings";
import { cn } from "@/lib/utils";

type TodoPanelProps = {
  recordId: string;
  onOpenSummary: () => void;
};

export function TodoPanel({ recordId, onOpenSummary }: TodoPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const todos = useQuery({
    queryKey: recordKeys.todos(recordId),
    queryFn: () => recordApi.getTodos(recordId),
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: recordKeys.todos(recordId) });
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
    onSuccess: () => void invalidate(),
  });

  if (todos.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("record.detail.todo.loading")}
      </p>
    );
  }
  if (todos.isError) {
    return (
      <Empty className="max-w-reading items-start p-0 text-left">
        <EmptyHeader className="items-start text-left">
          <EmptyTitle role="heading" aria-level={2}>
            {t("record.detail.todo.readErrorTitle")}
          </EmptyTitle>
          <EmptyDescription>{todos.error.message}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="items-start">
          <Button variant="outline" onClick={() => void todos.refetch()}>
            {t("record.detail.retry")}
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  const data = todos.data;
  // 手动增删改勾与生成门控解耦：blocked_reason 只影响 AI 生成入口（后续票），
  // 这里仅在清单为空时给出下一步指引。
  const showSummaryAction =
    data.blocked_reason === "SUMMARY_NOT_CONFIRMED" ||
    data.blocked_reason === "SUMMARY_SUPERSEDED" ||
    data.blocked_reason === "PROVIDER_NOT_CONFIGURED";

  return (
    <div className="max-w-reading min-w-0">
      {data.items.length ? (
        <section aria-labelledby="todo-list-title">
          <h2
            id="todo-list-title"
            className="text-section font-section text-ink"
          >
            {t("record.detail.todo.listTitle")}
          </h2>
          <ul className="mt-3">
            {data.items.map((item) => (
              <TodoRow key={item.id} item={item} recordId={recordId} />
            ))}
          </ul>
        </section>
      ) : data.blocked_reason ? (
        <Empty className="items-start p-0 text-left">
          <EmptyHeader className="items-start text-left">
            <EmptyTitle role="heading" aria-level={2}>
              {t(`record.detail.todo.blocked.${data.blocked_reason}.title`)}
            </EmptyTitle>
            <EmptyDescription>
              {t(
                `record.detail.todo.blocked.${data.blocked_reason}.description`,
              )}
            </EmptyDescription>
          </EmptyHeader>
          {showSummaryAction ? (
            <EmptyContent className="items-start">
              <Button variant="outline" onClick={onOpenSummary}>
                {t("record.detail.todo.openSummary")}
              </Button>
            </EmptyContent>
          ) : data.blocked_reason === "CONSENT_REQUIRED" ? (
            <EmptyContent className="items-start">
              <Button
                variant="outline"
                disabled={consent.isPending}
                onClick={() => consent.mutate()}
              >
                {consent.isPending ? (
                  <Spinner data-icon="inline-start" aria-hidden="true" />
                ) : null}
                {t("record.detail.todo.grantConsent")}
              </Button>
              {consent.isError ? (
                <p role="alert" className="text-body text-destructive">
                  {consent.error.message}
                </p>
              ) : null}
            </EmptyContent>
          ) : null}
        </Empty>
      ) : null}

      <AddTodoForm
        recordId={recordId}
        className={data.items.length ? "border-border mt-8 border-t pt-6" : undefined}
      />
    </div>
  );
}

function TodoRow({ item, recordId }: { item: TodoOut; recordId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.content);
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: recordKeys.todos(recordId) });
  const update = useMutation({
    mutationFn: (content: string) =>
      recordApi.updateTodo(recordId, item.id, content),
    onSuccess: () => {
      setEditing(false);
      void invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => recordApi.deleteTodo(recordId, item.id),
    onSuccess: () => void invalidate(),
  });
  const toggle = useMutation({
    mutationFn: (status: components["schemas"]["TodoStatus"]) =>
      recordApi.toggleTodo(recordId, item.id, status),
    onSuccess: () => void invalidate(),
  });
  const done = item.status === "DONE";
  const mutationError = update.error ?? remove.error ?? toggle.error ?? null;

  if (editing) {
    return (
      <li className="border-border border-t py-4 first:border-t-0">
        <form
          className="flex flex-wrap items-start gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const content = draft.trim();
            if (content) update.mutate(content);
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={500}
            aria-label={t("record.detail.todo.editInputLabel", {
              content: item.content,
            })}
            className="min-w-0 flex-1"
          />
          <Button type="submit" disabled={!draft.trim() || update.isPending}>
            {update.isPending ? <Spinner aria-hidden="true" /> : null}
            {t("record.detail.todo.save")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={update.isPending}
            onClick={() => {
              setEditing(false);
              setDraft(item.content);
              update.reset();
            }}
          >
            {t("record.detail.todo.cancelEdit")}
          </Button>
        </form>
        {update.isError ? (
          <p role="alert" className="text-body text-destructive mt-2">
            {update.error.message}
          </p>
        ) : null}
      </li>
    );
  }

  return (
    <li className="border-border border-t py-3 first:border-t-0">
      <div className="flex min-w-0 items-start gap-3">
        <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-3">
          <Checkbox
            checked={done}
            disabled={toggle.isPending}
            onCheckedChange={(checked) =>
              toggle.mutate(checked ? "DONE" : "TODO")
            }
            className="mt-1"
          />
          <span
            className={cn(
              "text-body text-ink min-w-0 flex-1 break-words",
              done && "text-muted-foreground line-through",
            )}
          >
            {item.content}
          </span>
        </label>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("record.detail.todo.edit", { content: item.content })}
            disabled={update.isPending || remove.isPending}
            onClick={() => {
              setDraft(item.content);
              setEditing(true);
              update.reset();
              remove.reset();
            }}
          >
            <Pencil aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("record.detail.todo.delete", {
              content: item.content,
            })}
            disabled={update.isPending || remove.isPending}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? (
              <Spinner data-icon="inline-start" aria-hidden="true" />
            ) : (
              <Trash2 aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>
      {mutationError ? (
        <p role="alert" className="text-body text-destructive mt-2">
          {mutationError.message}
        </p>
      ) : null}
    </li>
  );
}

function AddTodoForm({
  recordId,
  className,
}: {
  recordId: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const create = useMutation({
    mutationFn: (content: string) => recordApi.createTodo(recordId, content),
    onSuccess: () => {
      setContent("");
      void queryClient.invalidateQueries({
        queryKey: recordKeys.todos(recordId),
      });
    },
  });

  return (
    <form
      className={className}
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = content.trim();
        if (trimmed) create.mutate(trimmed);
      }}
    >
      <h2 className="text-section font-section text-ink">
        {t("record.detail.todo.addTitle")}
      </h2>
      <div className="mt-3 flex gap-2">
        <Input
          value={content}
          onChange={(event) => setContent(event.target.value)}
          maxLength={500}
          aria-label={t("record.detail.todo.inputLabel")}
          placeholder={t("record.detail.todo.placeholder")}
          className="min-w-0 flex-1"
        />
        <Button type="submit" disabled={!content.trim() || create.isPending}>
          {create.isPending ? <Spinner aria-hidden="true" /> : null}
          {t("record.detail.todo.add")}
        </Button>
      </div>
      {create.isError ? (
        <p role="alert" className="text-body text-destructive mt-3">
          {create.error.message}
        </p>
      ) : null}
    </form>
  );
}
