import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

// 检索结果项的纯展示部分（标题/摘录/所属课程名上下文），不绑定命令面板：
// 命令面板包一层 CommandItem 使用，资产库视图（04）可用自己的行容器复用。
export function SearchResultItem({
  icon: Icon,
  title,
  snippet,
  context,
  className,
}: {
  icon: LucideIcon;
  title: string;
  snippet: string;
  /** 所属课程名；课程结果与未归类记录/知识点为 null */
  context: string | null;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-start gap-2", className)}>
      <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm leading-5">{title}</p>
        <p className="text-muted-foreground truncate text-xs leading-4">
          {snippet}
        </p>
      </div>
      {context ? (
        <span className="text-muted-foreground max-w-24 shrink-0 truncate text-xs leading-5">
          {context}
        </span>
      ) : null}
    </div>
  );
}
