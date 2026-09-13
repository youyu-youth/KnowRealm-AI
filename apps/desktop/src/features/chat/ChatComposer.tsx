import { useTranslation } from "react-i18next";
import { ArrowUp, Globe, Plus, SlidersHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { cn } from "@/lib/utils";

type ChatComposerProps = {
  value: string;
  disabled: boolean;
  /** 禁用的用户可读原因（如挂载记录已删除），展示在输入区下方。 */
  disabledHint?: string;
  isStreaming: boolean;
  onValueChange: (value: string) => void;
  onSend: (content: string) => void;
  onStop: () => void;
};

const MESSAGE_MAX_LENGTH = 8000;

export function ChatComposer({
  value,
  disabled,
  disabledHint,
  isStreaming,
  onValueChange,
  onSend,
  onStop,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const webSearchEnabled = useChatUiStore((state) => state.tools.webSearch);
  const toggleTool = useChatUiStore((state) => state.toggleTool);

  function submit() {
    const content = value.trim();
    if (!content || disabled || isStreaming) return;
    onSend(content);
    onValueChange("");
  }

  return (
    <form
      className="flex flex-col gap-2 pt-4 pb-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="border-border-subtle bg-surface-raised focus-within:border-border-strong rounded-2xl border p-2.5 transition-colors">
        <Textarea
          value={value}
          rows={2}
          maxLength={MESSAGE_MAX_LENGTH}
          placeholder={t("chat.inputPlaceholder")}
          aria-label={t("chat.inputLabel")}
          disabled={disabled}
          className="max-h-44 resize-none border-transparent bg-transparent focus-visible:border-transparent focus-visible:ring-0 dark:bg-transparent"
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter 发送、Shift+Enter 换行。
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="mt-1 flex items-center justify-between gap-2 px-0.5">
          <div className="flex items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled
              aria-label={t("chat.attachment.action")}
            >
              <Plus aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-pressed={webSearchEnabled}
              aria-label={t("chat.tools.webSearch.title")}
              className={cn(webSearchEnabled && "text-chat-accent")}
              onClick={() => toggleTool("webSearch")}
            >
              <Globe aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled
              aria-label={t("chat.settings.action")}
            >
              <SlidersHorizontal aria-hidden="true" />
            </Button>
          </div>
          {isStreaming ? (
            <Button
              type="button"
              variant="outline"
              size="icon-lg"
              className="rounded-full"
              aria-label={t("chat.stop")}
              onClick={onStop}
            >
              <Square aria-hidden="true" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon-lg"
              className="rounded-full"
              aria-label={t("chat.send")}
              disabled={disabled}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>
      {disabled && disabledHint ? (
        <p className="text-label text-muted-foreground px-1">{disabledHint}</p>
      ) : null}
    </form>
  );
}
