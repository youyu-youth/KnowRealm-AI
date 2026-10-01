import { useQuery } from "@tanstack/react-query";
import { BookOpen, Info, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { appToast } from "@/components/common/appToastManager";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import {
  libraryApi,
  type LibraryItemOut,
} from "@/features/library/api/library";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import {
  useAddSharedRef,
  useRemoveSharedRef,
  useSharedRefs,
  type SharedRef,
} from "@/features/sharedRefs/api/sharedRefs";
import { ApiError } from "@/services/http/client";

type SharedRefsTabProps = { courseId: string };

/** 共享来源引用 Tab（工单 05）：本空间引用的外部资料清单与增删入口。
 *
 * 引用语义常驻提示（检索覆盖 + 资产只读）；失效为查询期派生——条目软删的
 * 引用行展示「来源已删除」仍可移除，回收站恢复即自动复活。 */
export function SharedRefsTab({ courseId }: SharedRefsTabProps) {
  const { t, i18n } = useTranslation();
  const refs = useSharedRefs(courseId);
  const [addOpen, setAddOpen] = useState(false);

  if (refs.isPending) {
    return (
      <p
        role="status"
        className="text-body text-ink-muted flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("sharedRefs.loading")}
      </p>
    );
  }
  if (refs.isError) {
    return (
      <div role="alert" className="grid gap-2">
        <h3 className="text-body-dense text-destructive font-medium">
          {t("sharedRefs.errorTitle")}
        </h3>
        <p className="text-label text-ink-muted">
          {t("sharedRefs.errorDescription")}
          <button
            type="button"
            className="text-ink ml-2 underline-offset-2 hover:underline"
            onClick={() => void refs.refetch()}
          >
            {t("sharedRefs.retry")}
          </button>
        </p>
      </div>
    );
  }

  const list = refs.data ?? [];
  return (
    <div className="grid gap-6">
      <Alert>
        <Info aria-hidden="true" className="size-4" />
        <AlertTitle>{t("sharedRefs.readonlyNotice.title")}</AlertTitle>
        <AlertDescription>
          {t("sharedRefs.readonlyNotice.description")}
        </AlertDescription>
      </Alert>
      <section
        aria-label={t("sharedRefs.list.sectionLabel")}
        className="bg-surface-raised border-border-subtle rounded-md border"
      >
        <div className="border-border-subtle flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
          <h2 className="text-section font-section text-ink-strong">
            {t("sharedRefs.list.sectionTitle")}
          </h2>
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" className="size-4" />
            {t("sharedRefs.add.open")}
          </Button>
        </div>
        {list.length === 0 ? (
          <div className="px-5 py-10">
            <Empty>
              <EmptyHeader>
                <EmptyMedia>
                  <BookOpen aria-hidden="true" className="size-5" />
                </EmptyMedia>
                <EmptyTitle>{t("sharedRefs.empty.title")}</EmptyTitle>
                <EmptyDescription>
                  {t("sharedRefs.empty.description")}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </div>
        ) : (
          <ul className="divide-border-subtle divide-y">
            {list.map((entry) => (
              <SharedRefRow
                key={entry.library_item_id}
                courseId={courseId}
                entry={entry}
                locale={i18n.resolvedLanguage}
              />
            ))}
          </ul>
        )}
      </section>
      <AddSharedRefDialog
        courseId={courseId}
        open={addOpen}
        onOpenChange={setAddOpen}
        existingIds={new Set(list.map((entry) => entry.library_item_id))}
      />
    </div>
  );
}

/** 引用行：条目身份 + 归属空间 + 失效提示（来源已删除）+ 移除入口。
 * 移除只解除本空间引用（原资料不动），轻量可逆操作，直接执行经 toast 回执。 */
function SharedRefRow({
  courseId,
  entry,
  locale,
}: {
  courseId: string;
  entry: SharedRef;
  locale: string | undefined;
}) {
  const { t } = useTranslation();
  const remove = useRemoveSharedRef(courseId);
  return (
    <li className="flex min-w-0 items-start gap-3 px-5 py-3">
      <div className="min-w-0 flex-1">
        <p
          className={
            entry.available
              ? "text-body text-ink-strong"
              : "text-body text-ink-faint line-through"
          }
        >
          {entry.title}
        </p>
        <p className="text-label text-ink-muted mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusTag>{t(`library.sourceTypes.${entry.source_type}`)}</StatusTag>
          {entry.owner_course_name ? (
            <span>
              {t("sharedRefs.list.owner", { course: entry.owner_course_name })}
            </span>
          ) : (
            <span>{t("sharedRefs.list.unclassified")}</span>
          )}
          <span>
            {new Intl.DateTimeFormat(locale, {
              year: "numeric",
              month: "short",
              day: "numeric",
            }).format(new Date(entry.created_at))}
          </span>
          {!entry.available ? (
            <span className="text-destructive">
              {t("sharedRefs.list.sourceDeleted")}
            </span>
          ) : null}
        </p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        disabled={remove.isPending}
        aria-label={t("sharedRefs.remove.label", { title: entry.title })}
        onClick={() =>
          remove.mutate(entry.library_item_id, {
            onError: (error) =>
              appToast.add({
                description:
                  error instanceof ApiError && error.message
                    ? error.message
                    : t("sharedRefs.remove.failed"),
              }),
          })
        }
      >
        <Trash2 aria-hidden="true" className="size-4" />
        {t("sharedRefs.remove.action")}
      </Button>
    </li>
  );
}

/** 添加引用对话框：列出可引用的资料条目（排除本空间归属与已引用），单选确认。
 * 未归类与其他空间的条目均可引用；后端仍是执法边界（OWNED / DUPLICATE 稳定
 * 错误码经 toast 呈现）。标题搜索复用资料库列表 API（q 参数，全库范围命中
 * ——首屏之外与首屏全被过滤的场景靠搜索触达）。 */
function AddSharedRefDialog({
  courseId,
  open,
  onOpenChange,
  existingIds,
}: {
  courseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingIds: Set<string>;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 250);
  // 可选清单随对话框打开取（引用关系变化不影响资料库清单本身）。
  const items = useSharedRefCandidates(
    courseId,
    open,
    existingIds,
    debouncedSearch,
  );
  const add = useAddSharedRef(courseId);

  const close = () => {
    setSelected(null);
    setSearch("");
    onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("sharedRefs.add.title")}</DialogTitle>
          <DialogDescription>
            {t("sharedRefs.add.description")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <div className="relative">
            <Search
              aria-hidden="true"
              className="text-ink-muted pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("sharedRefs.add.searchPlaceholder")}
              className="pl-9"
              aria-label={t("sharedRefs.add.searchPlaceholder")}
            />
          </div>
          {items.isPending ? (
            <p
              role="status"
              className="text-body text-ink-muted flex items-center gap-2 py-6"
            >
              <Spinner aria-hidden="true" />
              {t("sharedRefs.add.loading")}
            </p>
          ) : items.isError ? (
            <p role="alert" className="text-label text-destructive py-6">
              {t("sharedRefs.add.loadFailed")}
            </p>
          ) : items.data && items.data.length > 0 ? (
            <RadioGroup
              value={selected ?? undefined}
              onValueChange={(value) => setSelected(String(value))}
              className="divide-border-subtle max-h-80 divide-y overflow-y-auto rounded-md border"
            >
              {items.data.map((item) => (
                <label
                  key={item.id}
                  className="flex cursor-pointer items-start gap-3 px-3 py-2.5"
                >
                  <RadioGroupItem value={item.id} className="mt-1" />
                  <span className="min-w-0 flex-1">
                    <span className="text-body-dense text-ink block truncate">
                      {item.title}
                    </span>
                    <span className="text-label text-ink-muted mt-0.5 flex items-center gap-2">
                      <StatusTag>
                        {t(`library.sourceTypes.${item.source_type}`)}
                      </StatusTag>
                      {item.course_name
                        ? t("sharedRefs.list.owner", {
                            course: item.course_name,
                          })
                        : t("sharedRefs.list.unclassified")}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          ) : items.truncated ? (
            <p className="text-body text-ink-muted py-6">
              {t("sharedRefs.add.truncated", { count: items.loadedCount })}
            </p>
          ) : (
            <p className="text-body text-ink-muted py-6">
              {t("sharedRefs.add.noCandidates")}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" disabled={add.isPending} onClick={close}>
            {t("sharedRefs.add.cancel")}
          </Button>
          <Button
            disabled={add.isPending || selected == null}
            onClick={() => {
              if (selected == null) return;
              add.mutate(selected, {
                onSuccess: close,
                onError: (error) =>
                  appToast.add({
                    description:
                      error instanceof ApiError && error.message
                        ? error.message
                        : t("sharedRefs.add.failed"),
                  }),
              });
            }}
          >
            {add.isPending
              ? t("sharedRefs.add.submitting")
              : t("sharedRefs.add.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 输入去抖（对齐 search 模块先例：输入 250ms 后触发查询）。 */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** 可引用候选：资料条目按标题搜索（q 传后端，全库范围命中）取单页（个人量级
 * 上限 100），前端过滤本空间归属、已软删与已引用；total 超出单页时 truncated
 * ——空态须提示仅列出部分而非「没有候选」。 */
function useSharedRefCandidates(
  courseId: string,
  enabled: boolean,
  existingIds: Set<string>,
  q: string,
) {
  const query = useQuery({
    queryKey: sharedRefsKeys.candidates(courseId, q),
    queryFn: () =>
      libraryApi.listItems({ limit: 100, q: q.trim() || undefined }),
    enabled,
  });
  const data = useMemo(
    () =>
      query.data?.items.filter(
        (item: LibraryItemOut) =>
          item.course_id !== courseId &&
          item.deleted_at == null &&
          !existingIds.has(item.id),
      ),
    [query.data, courseId, existingIds],
  );
  return {
    ...query,
    data,
    truncated: (query.data?.total ?? 0) > (query.data?.items.length ?? 0),
    loadedCount: query.data?.items.length ?? 0,
  };
}
