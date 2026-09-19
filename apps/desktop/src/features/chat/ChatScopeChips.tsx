import { useTranslation } from "react-i18next";
import { FileText, GraduationCap, Library, MessageCircle } from "lucide-react";
import type { ChatSession } from "@/features/chat/api/types";
import { cn } from "@/lib/utils";

export type ScopeChipId = "free" | "record" | "course" | "all" | "libraryItem";

type ChatScopeChipsProps = {
  scope: ChatSession["scope"];
  /** 点击非当前范围胶囊：由宿主承接「新建会话」流程（范围会话内不可变，spec 根决策 2）。 */
  onSelectScope: (scope: ScopeChipId) => void;
  disabled?: boolean;
};

// LIBRARY_ITEM 不进全局范围切换（仅资料详情「AI 解读」入口创建）：映射到
// 无对应胶囊的 id，即资料会话中无胶囊高亮。
const CHIP_BY_SCOPE: Record<ChatSession["scope"], ScopeChipId> = {
  FREE: "free",
  RECORD: "record",
  LIBRARY_ITEM: "libraryItem",
  COURSE: "course",
  ALL: "all",
};

/**
 * 对话范围胶囊（图 1 对齐）：当前会话范围高亮；点其它胶囊 = 发起对应范围的新会话。
 */
export function ChatScopeChips({
  scope,
  onSelectScope,
  disabled,
}: ChatScopeChipsProps) {
  const { t } = useTranslation();
  const activeChip = CHIP_BY_SCOPE[scope];
  const scopes: {
    id: ScopeChipId;
    icon: typeof MessageCircle;
    label: string;
  }[] = [
    { id: "free", icon: MessageCircle, label: t("chat.scope.free") },
    { id: "record", icon: FileText, label: t("chat.scope.record") },
    { id: "course", icon: GraduationCap, label: t("chat.scope.course") },
    { id: "all", icon: Library, label: t("chat.scope.all") },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {scopes.map((scopeChip) => {
        const Icon = scopeChip.icon;
        const active = scopeChip.id === activeChip;
        return (
          <button
            key={scopeChip.id}
            type="button"
            disabled={disabled}
            aria-current={active ? "true" : undefined}
            aria-label={
              active
                ? scopeChip.label
                : t("chat.scope.switchTo", { scope: scopeChip.label })
            }
            title={
              active
                ? undefined
                : t("chat.scope.switchTo", { scope: scopeChip.label })
            }
            className={cn(
              "text-label inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 transition-colors",
              active
                ? "border-primary bg-primary text-primary-foreground font-medium"
                : "border-border-subtle bg-surface-raised text-ink-muted hover:text-ink",
            )}
            onClick={() => {
              if (!active) onSelectScope(scopeChip.id);
            }}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {scopeChip.label}
          </button>
        );
      })}
    </div>
  );
}
