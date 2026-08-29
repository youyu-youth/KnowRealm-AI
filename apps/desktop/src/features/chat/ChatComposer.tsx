import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ChatComposerProps = {
  disabled: boolean;
  /** 禁用的用户可读原因（如挂载记录已删除），展示在输入区下方。 */
  disabledHint?: string;
  isStreaming: boolean;
  initialValue?: string;
  onSend: (content: string) => void;
  onStop: () => void;
};

const MESSAGE_MAX_LENGTH = 8000;

export function ChatComposer({
  disabled,
  disabledHint,
  isStreaming,
  initialValue = "",
  onSend,
  onStop,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialValue);

  function submit() {
    const content = value.trim();
    if (!content || disabled || isStreaming) return;
    onSend(content);
    setValue("");
  }

  return (
    <form
      className="border-border flex flex-col gap-2 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="flex items-end gap-2">
        <Textarea
          value={value}
          rows={2}
          maxLength={MESSAGE_MAX_LENGTH}
          placeholder={t("chat.inputPlaceholder")}
          aria-label={t("chat.inputLabel")}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            // Enter 发送、Shift+Enter 换行。
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {isStreaming ? (
          <Button type="button" variant="outline" onClick={onStop}>
            <Square data-icon="inline-start" aria-hidden="true" />
            {t("chat.stop")}
          </Button>
        ) : (
          <Button type="submit" disabled={disabled}>
            <Send data-icon="inline-start" aria-hidden="true" />
            {t("chat.send")}
          </Button>
        )}
      </div>
      {disabled && disabledHint ? (
        <p className="text-label text-muted-foreground">{disabledHint}</p>
      ) : null}
    </form>
  );
}
