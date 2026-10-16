import { Globe, Loader2, Plus, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import {
  libraryApi,
  type LibraryIngestAccepted,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/services/http/client";

export type IngestTab = "web" | "file" | "text";

export type AddLibraryItemInitial = {
  courseId?: string;
  tab?: IngestTab;
  url?: string;
  originUri?: string;
  title?: string;
};

/**
 * 「添加资料」统一入库对话框（工单 03）：网页 URL / 本地文件 / 纯文本三路。
 * 判重 409 不静默合并——内联提示「打开已有条目 / 仍然保留」；
 * 网页抓取失败的降级路径经 initial 以 TEXT 标签预填原 URL 与标题进入。
 */
export function AddLibraryItemDialog({
  open,
  onOpenChange,
  initial,
  onOpenItem,
  onAccepted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: AddLibraryItemInitial;
  onOpenItem: (itemId: string) => void;
  onAccepted?: (result: LibraryIngestAccepted) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<IngestTab>(initial?.tab ?? "web");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [originUri, setOriginUri] = useState(initial?.originUri ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [courseId, setCourseId] = useState<string | null>(
    initial?.courseId ?? null,
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicateId, setDuplicateId] = useState<string | null>(null);

  // 对话框常挂载：open 翻转为 true 时按 initial 重新初始化（降级粘贴等
  // 预填入口因此生效），关闭不清理（下次打开重置）。
  const prevOpen = useRef(false);
  useEffect(() => {
    if (open && !prevOpen.current) {
      setTab(initial?.tab ?? "web");
      setUrl(initial?.url ?? "");
      setOriginUri(initial?.originUri ?? "");
      setTitle(initial?.title ?? "");
      setContent("");
      setFile(null);
      setError(null);
      setDuplicateId(null);
    }
    prevOpen.current = open;
  }, [open, initial]);

  const close = (next: boolean) => {
    onOpenChange(next);
  };

  const submit = async (allowDuplicate: boolean) => {
    setError(null);
    setDuplicateId(null);
    setPending(true);
    try {
      let accepted: LibraryIngestAccepted;
      if (tab === "web") {
        accepted = await libraryApi.ingest({
          source: "web",
          url: url.trim(),
          course_id: courseId,
          allow_duplicate: allowDuplicate,
        });
      } else if (tab === "text") {
        accepted = await libraryApi.ingest({
          source: "text",
          title: title.trim() || null,
          content,
          origin_uri: originUri.trim() || null,
          course_id: courseId,
          allow_duplicate: allowDuplicate,
        });
      } else {
        if (file === null) {
          setError(t("library.ingest.errors.noFile"));
          return;
        }
        accepted = await libraryApi.ingestFile(file, {
          courseId: courseId ?? undefined,
          allowDuplicate,
        });
      }
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
      // 立即可见 + 处理状态由列表轮询派生（解析中 → 可检索/失败）。
      close(true);
      onAccepted?.(accepted);
      return accepted;
    } catch (exc) {
      if (exc instanceof ApiError) {
        if (exc.code === "LIBRARY_ITEM_DUPLICATE_CONTENT") {
          const existing =
            typeof exc.params?.existing_item_id === "string"
              ? exc.params.existing_item_id
              : null;
          setDuplicateId(existing);
        } else {
          setError(exc.message);
        }
      } else {
        setError(t("library.ingest.errors.generic"));
      }
      return null;
    } finally {
      setPending(false);
    }
  };

  const webReady = tab !== "web" || url.trim().length > 0;
  const textReady = tab !== "text" || content.trim().length > 0;
  const fileReady = tab !== "file" || file !== null;
  const canSubmit = webReady && textReady && fileReady && !pending;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("library.ingest.title")}</DialogTitle>
          <DialogDescription>
            {t("library.ingest.description")}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(next) => setTab(next as IngestTab)}>
          <TabsList className="w-full justify-start">
            <TabsTrigger value="web">
              <Globe className="size-4" aria-hidden />
              {t("library.ingest.tabs.web")}
            </TabsTrigger>
            <TabsTrigger value="file">
              <Upload className="size-4" aria-hidden />
              {t("library.ingest.tabs.file")}
            </TabsTrigger>
            <TabsTrigger value="text">
              {t("library.ingest.tabs.text")}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="space-y-3">
          {tab === "web" ? (
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder={t("library.ingest.urlPlaceholder")}
              aria-label={t("library.ingest.urlLabel")}
              type="url"
            />
          ) : null}

          {tab === "file" ? (
            <div className="space-y-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.pdf,.docx"
                aria-label={t("library.ingest.filePicker")}
                className="hidden"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="size-4" aria-hidden />
                {file ? file.name : t("library.ingest.filePicker")}
              </Button>
              {file ? (
                <p className="text-muted-foreground text-label">
                  {t("library.ingest.fileSelected", { name: file.name })}
                </p>
              ) : null}
            </div>
          ) : null}

          {tab === "text" ? (
            <div className="space-y-2">
              {originUri ? (
                <p className="text-muted-foreground text-label">
                  {t("library.ingest.downgradeHint", { url: originUri })}
                </p>
              ) : null}
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t("library.ingest.titlePlaceholder")}
                aria-label={t("library.ingest.titleLabel")}
              />
              <Textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder={t("library.ingest.contentPlaceholder")}
                aria-label={t("library.ingest.contentLabel")}
                rows={8}
                className="field-sizing-fixed"
              />
            </div>
          ) : null}

          <ActiveCourseSelect
            id="library-ingest-course"
            value={courseId}
            onValueChange={setCourseId}
          />

          {error ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {duplicateId ? (
            <Alert role="alert">
              <AlertDescription>
                {t("library.ingest.duplicateHint")}
              </AlertDescription>
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    close(true);
                    onOpenItem(duplicateId);
                  }}
                >
                  {t("library.ingest.openExisting")}
                </Button>
                <Button
                  size="sm"
                  disabled={pending}
                  onClick={() => void submit(true)}
                >
                  {t("library.ingest.keepDuplicate")}
                </Button>
              </div>
            </Alert>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => close(true)}>
              {t("library.ingest.cancel")}
            </Button>
            <Button
              disabled={!canSubmit}
              onClick={() => void submit(false)}
              data-testid="library-ingest-submit"
            >
              {pending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Plus className="size-4" aria-hidden />
              )}
              {t("library.ingest.submit")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
