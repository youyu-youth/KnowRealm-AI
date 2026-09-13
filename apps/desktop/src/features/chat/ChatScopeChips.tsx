import { useTranslation } from "react-i18next";
import { FileText, GraduationCap, Library, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ChatScopeChipsProps = {
  recordId: string | null;
};

/**
 * 对话范围示意（图 1 对齐）：自由聊天/记录由会话真实挂载决定高亮；
 * 课程与全部资料尚未支持，仅展示并标注，不参与任何请求。
 */
export function ChatScopeChips({ recordId }: ChatScopeChipsProps) {
  const { t } = useTranslation();
  const free = recordId === null;
  const scopes = [
    {
      id: "free",
      icon: MessageCircle,
      active: free,
      label: t("chat.scope.free"),
    },
    {
      id: "record",
      icon: FileText,
      active: !free,
      label: t("chat.scope.record"),
    },
    {
      id: "course",
      icon: GraduationCap,
      active: false,
      label: t("chat.scope.course"),
    },
    {
      id: "all",
      icon: Library,
      active: false,
      label: t("chat.scope.all"),
    },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {scopes.map((scope) => {
        const Icon = scope.icon;
        const unavailable = scope.id === "course" || scope.id === "all";
        return (
          <span
            key={scope.id}
            aria-current={scope.active ? "true" : undefined}
            aria-label={
              unavailable
                ? t("chat.scope.unavailable", { scope: scope.label })
                : scope.label
            }
            title={
              unavailable
                ? t("chat.scope.unavailable", { scope: scope.label })
                : undefined
            }
            className={cn(
              "text-label inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 transition-colors",
              scope.active
                ? "border-primary bg-primary text-primary-foreground font-medium"
                : unavailable
                  ? "border-border-subtle text-muted-foreground/70 bg-transparent"
                  : "border-border-subtle bg-surface-raised text-ink-muted",
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {scope.label}
          </span>
        );
      })}
    </div>
  );
}
