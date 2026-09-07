import { useNavigate } from "@tanstack/react-router";
import {
  ClipboardPaste,
  FileText,
  GraduationCap,
  Mic,
  NotebookPen,
  Star,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSearchResults } from "@/features/search/api/queries";
import type {
  SearchCourseItem,
  SearchKnowledgePointItem,
  SearchRecordItem,
} from "@/features/search/api/search";
import { SearchResultItem } from "@/features/search/components/SearchResultItem";

export type PaletteCaptureCommand =
  "capture.record" | "capture.note" | "capture.paste";

// 面板内的捕获命令复用顶栏 capture.* 文案与入口；命令注册表仅此 3 项（spec 裁决）。
const captureCommands = [
  { labelKey: "capture.record", icon: Mic },
  { labelKey: "capture.note", icon: NotebookPen },
  { labelKey: "capture.paste", icon: ClipboardPaste },
] as const satisfies ReadonlyArray<{
  labelKey: PaletteCaptureCommand;
  icon: typeof Mic;
}>;

export function CommandPalette({
  open,
  onOpenChange,
  onCaptureCommand,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCaptureCommand: (command: PaletteCaptureCommand) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  // 关闭时清空查询：重新打开回到命令态，不带出上次的查询与结果。
  const handleOpenChange = (next: boolean) => {
    if (!next) setQuery("");
    onOpenChange(next);
  };

  // Ctrl+K 应用内全局唤起：React keydown 监听、硬编码，不进偏好改键体系。
  // 排除 Alt/Shift/Meta 组合，避免误吞 OS 全局快捷键（如速记/录音的 Ctrl+Alt+*）。
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (open) return;
      if (
        event.ctrlKey &&
        !event.altKey &&
        !event.metaKey &&
        !event.shiftKey &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        onOpenChange(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  const trimmed = query.trim();
  const search = useSearchResults(trimmed);
  const results = search.data;
  const hasQuery = trimmed.length > 0;

  // 客户端过滤只作用于 3 个命令项（子串匹配）；资产结果由服务端 FTS5 决定。
  const visibleCommands = hasQuery
    ? captureCommands.filter(({ labelKey }) =>
        t(labelKey).toLowerCase().includes(trimmed.toLowerCase()),
      )
    : captureCommands;

  // 空态门：已有当前去抖键的已完成结果且不在拉取中才渲染（去抖/请求窗口不闪空态）；
  // 命令项是否残留由 cmdk 自身的零项判定兜底（有项时 Empty 不渲染）。
  const showEmpty = results !== undefined && !search.isFetching;

  const selectCourse = (item: SearchCourseItem) => {
    handleOpenChange(false);
    void navigate({
      to: "/spaces/$courseId",
      params: { courseId: item.id },
      search: { tab: "overview" },
    });
  };
  const selectRecord = (item: SearchRecordItem) => {
    handleOpenChange(false);
    void navigate({
      to: "/records/$recordId",
      params: { recordId: item.id },
    });
  };
  const selectKnowledgePoint = (item: SearchKnowledgePointItem) => {
    handleOpenChange(false);
    void navigate({
      to: "/records/$recordId",
      params: { recordId: item.record_id },
      search: { tab: "knowledge-points" },
    });
  };

  // 定制点（不改 components/ui 生成代码）：ui 的 CommandDialog 不透传 shouldFilter，
  // 服务端 FTS5 检索须关客户端过滤，故用 Dialog + Command 自组合，等价于 CommandDialog。
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="overflow-hidden p-0 sm:max-w-lg"
      >
        <div className="sr-only">
          <DialogTitle>{t("commandPalette.title")}</DialogTitle>
          <DialogDescription>
            {t("commandPalette.description")}
          </DialogDescription>
        </div>
        <Command shouldFilter={false} loop>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder={t("commandPalette.placeholder")}
          />
          <CommandList>
            {visibleCommands.length > 0 ? (
              <CommandGroup heading={t("commandPalette.commandsGroup")}>
                {visibleCommands.map(({ labelKey, icon: Icon }) => (
                  <CommandItem
                    key={labelKey}
                    value={labelKey}
                    onSelect={() => {
                      handleOpenChange(false);
                      onCaptureCommand(labelKey);
                    }}
                  >
                    <Icon aria-hidden="true" />
                    {t(labelKey)}
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
            {results ? (
              <>
                {results.courses.length > 0 ? (
                  <CommandGroup heading={t("commandPalette.coursesGroup")}>
                    {results.courses.map((item) => (
                      <CommandItem
                        key={`course:${item.id}`}
                        value={`course:${item.id}`}
                        onSelect={() => selectCourse(item)}
                      >
                        <SearchResultItem
                          icon={GraduationCap}
                          title={item.title}
                          snippet={item.snippet}
                          context={null}
                        />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null}
                {results.records.length > 0 ? (
                  <CommandGroup heading={t("commandPalette.recordsGroup")}>
                    {results.records.map((item) => (
                      <CommandItem
                        key={`record:${item.id}`}
                        value={`record:${item.id}`}
                        onSelect={() => selectRecord(item)}
                      >
                        <SearchResultItem
                          icon={FileText}
                          title={item.title}
                          snippet={item.snippet}
                          context={item.course_name}
                        />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null}
                {results.knowledge_points.length > 0 ? (
                  <CommandGroup
                    heading={t("commandPalette.knowledgePointsGroup")}
                  >
                    {results.knowledge_points.map((item) => (
                      <CommandItem
                        key={`kp:${item.id}`}
                        value={`kp:${item.id}`}
                        onSelect={() => selectKnowledgePoint(item)}
                      >
                        <SearchResultItem
                          icon={Star}
                          title={item.title}
                          snippet={item.snippet}
                          context={item.course_name}
                        />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null}
              </>
            ) : null}
            {hasQuery && showEmpty ? (
              <CommandEmpty>{t("commandPalette.noResults")}</CommandEmpty>
            ) : null}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
